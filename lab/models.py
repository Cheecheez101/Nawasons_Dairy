from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.utils import OperationalError, ProgrammingError
from django.db.models import Sum
from django.utils import timezone
from django.utils.timezone import is_naive, make_aware

try:  # Python 3.9+
	from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - fallback for very old runtimes
	ZoneInfo = None
	ZoneInfoNotFoundError = Exception


class MilkYield(models.Model):
	# Allowed intake windows (local time) for automated session assignment
	COLLECTION_WINDOWS = [
		{"key": "morning", "label": "Morning", "start": time(0, 0), "end": time(6, 0)},
		{"key": "afternoon", "label": "Afternoon", "start": time(12, 0), "end": time(15, 0)},
		{"key": "evening", "label": "Evening", "start": time(16, 0), "end": time(19, 0)},
	]

	SESSION_CHOICES = [(window["key"], window["label"]) for window in COLLECTION_WINDOWS]
	_window_cache = None

	# Add an Unassigned option to allow clerk to record yields without picking a tank
	TANK_CAPACITY_LITRES = {
		"Unassigned": Decimal("0"),
		"Tank A": Decimal("500"),
		"Tank B": Decimal("750"),
		"Tank C": Decimal("1000"),
		"Spoilt Tank": Decimal("500"),
	}

	QUALITY_CHOICES = [
		("premium", "Premium"),
		("standard", "Standard"),
		("low", "Low"),
	]

	QUALITY_SCORES = {
		"premium": 98,
		"standard": 85,
		"low": 70,
	}

	cow = models.ForeignKey("production.Cow", on_delete=models.CASCADE, related_name="yields")
	recorded_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="milk_yields_recorded",
	)
	recorded_at = models.DateTimeField(auto_now_add=True)
	session = models.CharField(max_length=20, choices=SESSION_CHOICES, default="morning")
	collection_window_start = models.DateTimeField(null=True, blank=True, editable=False)
	collection_window_end = models.DateTimeField(null=True, blank=True, editable=False)
	yield_litres = models.DecimalField(max_digits=6, decimal_places=2)
	storage_tank = models.CharField(
		max_length=40,
		choices=[(tank, tank) for tank in TANK_CAPACITY_LITRES.keys()],
		default="Unassigned",
	)
	storage_level_percentage = models.PositiveIntegerField(editable=False, default=0)
	quality_grade = models.CharField(max_length=20, choices=QUALITY_CHOICES, default="standard")
	quality_score = models.PositiveSmallIntegerField(default=85, editable=False)
	quality_notes = models.TextField(blank=True)
	total_yield = models.DecimalField(max_digits=6, decimal_places=2, editable=False)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-recorded_at", "-created_at"]
		unique_together = ("cow", "recorded_at")
		permissions = [
			("approve_milk", "Can approve or reject milk quality"),
		]
		app_label = "production"

	def __str__(self):
		return f"{self.cow.cow_id} - {self.recorded_at}"

	@classmethod
	def _collection_timezone(cls):
		tz_name = getattr(settings, "MILK_COLLECTION_TIME_ZONE", None)
		cache_key = getattr(cls, "_collection_tz_name", None)
		if tz_name and cache_key == tz_name and getattr(cls, "_collection_tz", None):
			return cls._collection_tz

		resolved = None
		if tz_name and ZoneInfo:
			try:
				resolved = ZoneInfo(tz_name)
			except ZoneInfoNotFoundError:
				resolved = None
		if not resolved:
			resolved = timezone.get_current_timezone()

		cls._collection_tz = resolved
		cls._collection_tz_name = tz_name
		return resolved

	@classmethod
	def invalidate_window_cache(cls):
		cls._window_cache = None

	@classmethod
	def get_collection_windows(cls, force_refresh=False):
		if cls._window_cache is not None and not force_refresh:
			return cls._window_cache

		overrides = {}
		try:
			for override in CollectionWindowOverride.objects.select_related("updated_by"):
				overrides[override.session_key] = override
		except (OperationalError, ProgrammingError):  # pragma: no cover - migrations
			overrides = {}

		windows = []
		for window in cls.COLLECTION_WINDOWS:
			override = overrides.get(window["key"])
			windows.append({
				"key": window["key"],
				"label": window["label"],
				"start": override.start_time if override else window["start"],
				"end": override.end_time if override else window["end"],
				"default_start": window["start"],
				"default_end": window["end"],
				"override": bool(override),
				"updated_at": override.updated_at if override else None,
				"updated_by": override.updated_by if override else None,
			})

		cls._window_cache = windows
		return windows

	@classmethod
	def get_window_for_session(cls, session_key):
		if not session_key:
			return None
		for window in cls.get_collection_windows():
			if window["key"] == session_key:
				return window
		return None

	def _measurement_datetime(self):
		measurement_dt = self.recorded_at or timezone.now()
		if is_naive(measurement_dt):
			measurement_dt = make_aware(measurement_dt, timezone.get_current_timezone())
		return measurement_dt

	@classmethod
	def resolve_collection_session(cls, measurement_dt):
		measurement_dt = measurement_dt or timezone.now()
		if is_naive(measurement_dt):
			measurement_dt = make_aware(measurement_dt, timezone.get_current_timezone())
		localized = measurement_dt.astimezone(cls._collection_timezone())
		current_time = localized.time()
		for window in cls.get_collection_windows():
			start = window["start"]
			end = window["end"]
			if start <= end:
				in_window = start <= current_time < end
			else:
				in_window = current_time >= start or current_time < end
			if in_window:
				return window["key"]
		return None

	@classmethod
	def window_bounds_for_session(cls, measurement_dt, session_key):
		if not session_key:
			return (None, None)
		measurement_dt = measurement_dt or timezone.now()
		if is_naive(measurement_dt):
			measurement_dt = make_aware(measurement_dt, timezone.get_current_timezone())
		collection_tz = cls._collection_timezone()
		localized = measurement_dt.astimezone(collection_tz)
		window = cls.get_window_for_session(session_key)
		if not window:
			return (None, None)

		start_dt = datetime.combine(localized.date(), window["start"])
		end_dt = datetime.combine(localized.date(), window["end"])
		start_dt = start_dt.replace(tzinfo=collection_tz)
		end_dt = end_dt.replace(tzinfo=collection_tz)

		if window["end"] <= window["start"]:
			if localized.time() < window["end"]:
				start_dt -= timedelta(days=1)
			else:
				end_dt += timedelta(days=1)

		return (start_dt, end_dt)

	def _calculate_storage_level(self):
		capacity = self.TANK_CAPACITY_LITRES.get(self.storage_tank)
		if not capacity:
			return 0
		measurement_dt = self._measurement_datetime()
		existing = MilkYield.objects.filter(
			storage_tank=self.storage_tank,
			recorded_at__date=measurement_dt.date(),
		).exclude(pk=self.pk)
		current_total = existing.aggregate(total=Sum("yield_litres"))["total"] or Decimal("0")
		level = ((current_total + self.yield_litres) / capacity) * Decimal("100")
		return int(min(100, round(level)))

	@classmethod
	def is_session_available(cls, session_key, measurement_dt=None):
		if not session_key:
			return False
		measurement_dt = measurement_dt or timezone.now()
		if is_naive(measurement_dt):
			measurement_dt = make_aware(measurement_dt, timezone.get_current_timezone())
		batch = Batch.for_session(session_key, collection_date=measurement_dt.date(), create=False)
		if not batch:
			return True
		return batch.state == Batch.State.OPEN

	def save(self, *args, **kwargs):
		if not self.recorded_at:
			self.recorded_at = timezone.now()

		measurement_dt = self._measurement_datetime()
		resolved_session = self.resolve_collection_session(measurement_dt)
		effective_session = resolved_session or self.session

		if resolved_session:
			window_start, window_end = self.window_bounds_for_session(measurement_dt, resolved_session)
			self.session = resolved_session
		else:
			if not effective_session:
				raise ValidationError(
					"Milk collection is currently closed outside the configured intake windows."
				)
			if not self.is_session_available(effective_session, measurement_dt):
				raise ValidationError(
					"The selected batch window is closed. Ask the lab team to reopen it before recording more yields."
				)
			window_start, window_end = self.window_bounds_for_session(measurement_dt, effective_session)
			self.session = effective_session

		self.collection_window_start = window_start
		self.collection_window_end = window_end
		self.total_yield = self.yield_litres
		self.quality_score = self.QUALITY_SCORES.get(self.quality_grade, 85)
		self.storage_level_percentage = self._calculate_storage_level()
		super().save(*args, **kwargs)
		try:
			Batch.ensure_yield_assignment(self)
		except ValidationError:
			super().delete()
			raise


class CollectionWindowOverride(models.Model):
	session_key = models.CharField(
		max_length=20,
		choices=MilkYield.SESSION_CHOICES,
		unique=True,
	)
	start_time = models.TimeField()
	end_time = models.TimeField()
	updated_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="collection_window_overrides",
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["session_key"]
		verbose_name = "Collection window override"
		verbose_name_plural = "Collection window overrides"

	def __str__(self):
		return f"{self.session_key} override ({self.start_time} - {self.end_time})"

	def save(self, *args, **kwargs):
		super().save(*args, **kwargs)
		MilkYield.invalidate_window_cache()

	def delete(self, *args, **kwargs):
		result = super().delete(*args, **kwargs)
		MilkYield.invalidate_window_cache()
		return result


def default_collection_date():
	return timezone.localdate()


class Batch(models.Model):

	class State(models.TextChoices):
		OPEN = ("open", "Open")
		CLOSED = ("closed", "Closed")
		LOCKED = ("locked", "Locked")

	"""Groups multiple milk yields collected in the same intake session."""
	session = models.CharField(
		max_length=20,
		choices=MilkYield.SESSION_CHOICES,
	)
	auto_managed = models.BooleanField(
		default=True,
		help_text="If true, the system controls open/close transitions based on intake windows.",
	)
	collection_date = models.DateField(default=default_collection_date)
	state = models.CharField(max_length=20, choices=State.choices, default=State.OPEN)
	opened_at = models.DateTimeField(auto_now_add=True)
	reopened_at = models.DateTimeField(null=True, blank=True)
	closed_at = models.DateTimeField(null=True, blank=True)
	opened_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		related_name="opened_intake_batches",
		null=True,
		blank=True,
	)
	closed_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		related_name="closed_intake_batches",
		null=True,
		blank=True,
	)
	created_at = models.DateTimeField(auto_now_add=True)
	yields = models.ManyToManyField(MilkYield, related_name="batches", blank=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return f"{self.session} batch {self.id} ({self.collection_date:%Y-%m-%d})"

	@property
	def is_open(self):
		return self.state == self.State.OPEN

	@property
	def is_locked(self):
		return self.state == self.State.LOCKED

	def total_volume_litres(self):
		"""Return the combined yield volume for dashboards."""
		return self.yields.aggregate(total=Sum("yield_litres"))["total"] or Decimal("0")

	def open(self, *, user=None, save=True):
		if self.state == self.State.LOCKED:
			raise ValidationError("Batch is locked after lab approval and cannot be reopened.")
		self.state = self.State.OPEN
		self.closed_at = None
		self.closed_by = None
		self.reopened_at = timezone.now()
		if user:
			self.opened_by = user
		if save:
			self.save(update_fields=["state", "closed_at", "closed_by", "reopened_at", "opened_by"])

	def close(self, *, user=None, save=True):
		if self.state == self.State.LOCKED:
			raise ValidationError("Batch is already locked for lab processing.")
		self.state = self.State.CLOSED
		self.closed_at = timezone.now()
		if user:
			self.closed_by = user
		if save:
			update_fields = ["state", "closed_at"]
			if user:
				update_fields.append("closed_by")
			self.save(update_fields=update_fields)

	def lock(self, save=True):
		self.state = self.State.LOCKED
		if save:
			self.save(update_fields=["state"])

	@classmethod
	def for_session(cls, session_key, *, collection_date=None, create=True):
		collection_date = collection_date or timezone.localdate()
		batch = (
			cls.objects
			.filter(session=session_key, collection_date=collection_date)
			.order_by("-created_at")
			.first()
		)
		if batch:
			return batch
		if not create:
			return None
		return cls.objects.create(session=session_key, collection_date=collection_date)

	@classmethod
	def session_is_open(cls, session_key, *, collection_date=None):
		batch = cls.for_session(session_key, collection_date=collection_date, create=False)
		if not batch:
			return True
		return batch.state == cls.State.OPEN

	@classmethod
	def ensure_yield_assignment(cls, yield_obj):
		session_key = yield_obj.session
		if not session_key:
			return
		measurement_dt = yield_obj.recorded_at or timezone.now()
		if is_naive(measurement_dt):
			measurement_dt = make_aware(measurement_dt, timezone.get_current_timezone())
		batch = cls.for_session(session_key, collection_date=measurement_dt.date(), create=False)
		if not batch or batch.is_locked:
			batch = cls.objects.create(session=session_key, collection_date=measurement_dt.date())
		elif not batch.is_open:
			raise ValidationError("The selected batch is closed. Reopen it before recording new yields.")
		batch.yields.add(yield_obj)


class BatchTest(models.Model):
	RESULT_CHOICES = [
		("pending", "Pending"),
		("approved", "Approved"),
		("rejected", "Rejected"),
	]

	batch = models.OneToOneField(Batch, on_delete=models.CASCADE, related_name="test")
	tested_at = models.DateTimeField(auto_now_add=True)
	tested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
	fat_percentage = models.DecimalField(max_digits=5, decimal_places=2)
	snf_percentage = models.DecimalField(max_digits=5, decimal_places=2)
	acidity = models.DecimalField(max_digits=5, decimal_places=2)
	contaminants = models.TextField(blank=True, null=True)
	result = models.CharField(max_length=20, choices=RESULT_CHOICES, default="pending")

	class Meta:
		ordering = ["-tested_at"]

	def __str__(self):
		return f"Batch {self.batch_id} - {self.result}"

	def approve(self):
		self.result = "approved"
		self.save(update_fields=["result"])
		if hasattr(self, "batch") and self.batch_id:
			self.batch.lock()

	def reject(self, reason=None):
		self.result = "rejected"
		if reason:
			self.contaminants = reason
		update_fields = ["result"]
		if reason:
			update_fields.append("contaminants")
		self.save(update_fields=update_fields)
		if hasattr(self, "batch") and self.batch_id:
			self.batch.lock()

class LabBatchApproval(models.Model):
	RESULT_CHOICES = [
		("approved", "Approved"),
		("rejected", "Rejected"),
		("pending", "Pending"),
	]

	production_batch = models.OneToOneField(
		"production.ProductionBatch",
		on_delete=models.CASCADE,
		related_name="lab_approval",
		null=True,
		blank=True,
	)
	overall_result = models.CharField(max_length=20, choices=RESULT_CHOICES, default="pending")
	expiry_date = models.DateField(null=True, blank=True)
	approved_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name="lab_batch_approvals",
	)
	approved_at = models.DateTimeField(auto_now_add=True)
	remarks = models.TextField(blank=True)

	class Meta:
		ordering = ["-approved_at"]
		permissions = [
			("approve_milk_batch", "Can approve or reject milk batches"),
			("issue_expiry", "Can issue expiry dates for approved batches"),
		]

	def __str__(self):
		return f"Batch {self.production_batch_id} - {self.overall_result}"

	def set_expiry(self, shelf_life_days=7):
		self.expiry_date = timezone.now().date() + timedelta(days=shelf_life_days)
		self.save()

	def save(self, *args, **kwargs):
		result = super().save(*args, **kwargs)
		self._sync_production_batch_state()
		return result

	def _sync_production_batch_state(self):
		from production.models import ProductionBatch

		batch = self.production_batch
		if not batch:
			return

		if self.overall_result == "approved":
			desired_status = (
				ProductionBatch.Status.READY_FOR_STORE if self.expiry_date else ProductionBatch.Status.LAB_APPROVED
			)
		elif self.overall_result == "rejected":
			desired_status = ProductionBatch.Status.PENDING_LAB
		else:
			desired_status = ProductionBatch.Status.PENDING_LAB

		update_fields = []
		if batch.status != desired_status:
			batch.status = desired_status
			update_fields.append("status")

		if not batch.moved_to_lab:
			batch.moved_to_lab = True
			update_fields.append("moved_to_lab")

		if update_fields:
			batch.save(update_fields=update_fields)


