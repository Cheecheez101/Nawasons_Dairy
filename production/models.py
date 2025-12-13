from django.db import models
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.timezone import is_naive, make_aware

class Cow(models.Model):
    HEALTH_STATUSES = [
        ("healthy", "Healthy"),
        ("monitor", "Monitor"),
        ("sick", "Needs Attention"),
    ]

    cow_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=60, blank=True)
    breed = models.CharField(max_length=50)
    date_of_birth = models.DateField()
    health_status = models.CharField(max_length=20, choices=HEALTH_STATUSES, default="healthy")
    stall_location = models.CharField(max_length=50, blank=True)
    daily_capacity_litres = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["cow_id"]

    def __str__(self):
        return self.cow_id

    @property
    def age_in_days(self):
        return (timezone.now().date() - self.date_of_birth).days

    def latest_yield(self):
        return self.yields.order_by('-recorded_at').first()


class MilkYield(models.Model):
    SESSION_CHOICES = [
        ("morning", "Morning"),
        ("afternoon", "Afternoon"),
        ("evening", "Evening"),
    ]

    # Add an Unassigned option to allow clerk to record yields without picking a tank
    TANK_CAPACITY_LITRES = {
        "Unassigned": Decimal('0'),
        "Tank A": Decimal('500'),
        "Tank B": Decimal('750'),
        "Tank C": Decimal('1000'),
        "Spoilt Tank": Decimal('500'),
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

    cow = models.ForeignKey(Cow, on_delete=models.CASCADE, related_name='yields')
    recorded_at = models.DateTimeField(auto_now_add=True)
    session = models.CharField(max_length=20, choices=SESSION_CHOICES, default="morning")
    yield_litres = models.DecimalField(max_digits=6, decimal_places=2)
    storage_tank = models.CharField(max_length=40, choices=[(tank, tank) for tank in TANK_CAPACITY_LITRES.keys()], default="Unassigned")
    storage_level_percentage = models.PositiveIntegerField(editable=False, default=0)
    quality_grade = models.CharField(max_length=20, choices=QUALITY_CHOICES, default="standard")
    quality_score = models.PositiveSmallIntegerField(default=85, editable=False)
    quality_notes = models.TextField(blank=True)
    total_yield = models.DecimalField(max_digits=6, decimal_places=2, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Workflow flags
    raw_test_approved = models.BooleanField(default=False)      # set by Lab raw test
    tank_test_latest_status = models.CharField(max_length=20, default="pending")  # set by Lab tank test

    class Meta:
        ordering = ['-recorded_at', '-created_at']
        unique_together = ('cow', 'recorded_at')
        permissions = [
            ('approve_milk', 'Can approve or reject milk quality'),
        ]

    def __str__(self):
        return f"{self.cow.cow_id} - {self.recorded_at}"

    def _measurement_datetime(self):
        measurement_dt = self.recorded_at or timezone.now()
        if is_naive(measurement_dt):
            measurement_dt = make_aware(measurement_dt, timezone.get_current_timezone())
        return measurement_dt

    def _calculate_storage_level(self):
        capacity = self.TANK_CAPACITY_LITRES.get(self.storage_tank)
        if not capacity:
            return 0
        measurement_dt = self._measurement_datetime()
        existing = MilkYield.objects.filter(
            storage_tank=self.storage_tank,
            recorded_at__date=measurement_dt.date()
        ).exclude(pk=self.pk)
        current_total = existing.aggregate(total=Sum('yield_litres'))['total'] or Decimal('0')
        level = ((current_total + self.yield_litres) / capacity) * Decimal('100')
        return int(min(100, round(level)))

    def save(self, *args, **kwargs):
        if not self.recorded_at:
            self.recorded_at = timezone.now()
        self.total_yield = self.yield_litres
        self.quality_score = self.QUALITY_SCORES.get(self.quality_grade, 85)
        self.storage_level_percentage = self._calculate_storage_level()
        # enforce: raw milk must be approved before considered valid in tank workflows
        if not self.raw_test_approved:
            # We allow saving, but downstream consumption will be blocked until raw test approves.
            pass
        super().save(*args, **kwargs)


class ProductPrice(models.Model):
    inventory_item = models.OneToOneField(
        'inventory.InventoryItem',
        on_delete=models.PROTECT,
        related_name='product_price',
    )
    sku = models.CharField(max_length=30, unique=True)
    product_name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='product_prices',
    )

    class Meta:
        ordering = ['product_name']
        permissions = [
            ('view_productpricechangelog', 'Can view product price change logs'),
        ]

    def __str__(self):
        return f"{self.product_name} ({self.sku})"

    def save(self, *args, **kwargs):
        if self.inventory_item_id:
            self.sku = self.inventory_item.sku
            self.product_name = self.inventory_item.name
        previous_price = None
        if self.pk:
            previous_price = ProductPrice.objects.only('price').get(pk=self.pk).price
        super().save(*args, **kwargs)
        if self.updated_by_id and (previous_price is None or previous_price != self.price):
            ProductPriceChangeLog.objects.create(
                product_price=self,
                old_price=previous_price,
                new_price=self.price,
                changed_by=self.updated_by,
            )

    @classmethod
    def current_for_inventory(cls, inventory_item):
        try:
            return cls.objects.get(inventory_item=inventory_item)
        except cls.DoesNotExist:
            return None


class ProductPriceChangeLog(models.Model):
    product_price = models.ForeignKey(
        ProductPrice,
        on_delete=models.CASCADE,
        related_name='change_logs',
    )
    old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='product_price_change_logs',
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.product_price} changed at {self.changed_at:%Y-%m-%d %H:%M}"


class ProductionBatch(models.Model):
    PRODUCT_CHOICES = [
        ('atm', 'Fresh Milk ATM'),
        ('esl', 'ESL Milk'),
        ('yogurt', 'Yogurt'),
        ('mala', 'Mala'),
        ('ghee', 'Ghee'),
    ]

    milk_source = models.ForeignKey(MilkYield, on_delete=models.PROTECT, related_name="production_batches")
    product_type = models.CharField(max_length=20, choices=PRODUCT_CHOICES)
    sku = models.CharField(max_length=30)  # e.g. MALA-CL-500
    quantity_produced = models.DecimalField(max_digits=10, decimal_places=2)
    produced_at = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="production_batches")
    moved_to_lab = models.BooleanField(default=False)

    class Meta:
        ordering = ["-produced_at"]

    def __str__(self):
        return f"{self.product_type} batch {self.id} from {self.milk_source.storage_tank}"

    def consume_milk(self):
        """
        Deduct milk from source tank when batch is created.
        Enforce tank test approval and raw test approval before consumption.
        """
        if not self.milk_source.raw_test_approved:
            raise ValidationError("Raw milk not approved by Lab. Cannot consume from tank.")
        if self.milk_source.tank_test_latest_status != "approved":
            raise ValidationError("Tank batch not approved by Lab. Cannot consume from tank.")
        if self.milk_source.yield_litres < self.quantity_produced:
            raise ValidationError("Not enough milk in tank for this production batch")
        self.milk_source.yield_litres -= self.quantity_produced
        self.milk_source.save(update_fields=["yield_litres"])
        self.moved_to_lab = True
