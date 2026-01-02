from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Min, Sum, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from inventory.models import InventoryItem
from production.models import ProductionBatch
from storage.models import ColdStorageInventory

from .forms import BatchEditForm, BatchTestForm, LabBatchApprovalForm, SessionWindowFormSet
from .models import Batch, BatchTest, LabBatchApproval, MilkYield, CollectionWindowOverride

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
@login_required
@permission_required("lab.add_labbatchapproval", raise_exception=True)
def approve_batch(request, batch_id):
	batch = get_object_or_404(ProductionBatch, id=batch_id)
	approval = getattr(batch, "lab_approval", None)
	storage_record = getattr(batch, "storage_record", None)

	if request.method == "POST":
		form = LabBatchApprovalForm(request.POST, instance=approval, batch=batch, storage_record=storage_record)
		if form.is_valid():
			obj = form.save(commit=False)
			obj.production_batch = batch
			obj.approved_by = request.user

			shelf_days = form.cleaned_data.get("shelf_life_days") or 0
			if obj.overall_result == "approved" and not obj.expiry_date and shelf_days:
				obj.set_expiry(shelf_life_days=shelf_days)
			else:
				obj.save()

			storage_entry = form.save_storage_assignment(obj)
			form.sync_destination_tank()

			if storage_entry:
				messages.success(
					request,
					f"Batch approval saved and moved into {storage_entry.location.name}.",
				)
			else:
				messages.success(request, "Batch approval saved.")
			return redirect("lab:batch_tests")
	else:
		form = LabBatchApprovalForm(instance=approval, batch=batch, storage_record=storage_record)
	return render(request, "lab/approve_batch.html", {"form": form, "batch": batch})



@login_required
@permission_required("lab.view_batchtest", raise_exception=True)
def lab_dashboard(request):
	filters = {
		"batch_type": request.GET.get("batch_type", ""),
		"tank": request.GET.get("tank", ""),
		"product": request.GET.get("product", ""),
		"expiry_before": request.GET.get("expiry_before", ""),
	}

	today = timezone.now().date()
	session_windows = []
	for session_key, session_label in MilkYield.SESSION_CHOICES:
		batch = Batch.for_session(session_key, collection_date=today, create=False)
		total_litres = batch.total_volume_litres() if batch else Decimal("0")
		state = batch.state if batch else Batch.State.OPEN
		session_windows.append(
			{
				"key": session_key,
				"label": session_label,
				"state": state,
				"is_open": batch.is_open if batch else True,
				"is_locked": batch.is_locked if batch else False,
				"batch_id": batch.id if batch else None,
				"litres": total_litres,
				"opened_at": batch.opened_at if batch else None,
				"closed_at": batch.closed_at if batch else None,
				"collection_date": today,
			}
		)

	open_batches = (
		Batch.objects.filter(state=Batch.State.OPEN)
		.annotate(sample_count=Count("yields", distinct=True), total_litres=Sum("yields__yield_litres"))
		.order_by("-collection_date", "-opened_at")[:15]
	)

	closed_batches = (
		Batch.objects.filter(state=Batch.State.CLOSED)
		.annotate(sample_count=Count("yields", distinct=True), total_litres=Sum("yields__yield_litres"))
		.order_by("-collection_date", "-closed_at")[:15]
	)

	def build_status(state, label):
		icon_map = {"pass": "✅", "fail": "❌", "pending": "⏳"}
		return {"icon": icon_map[state], "label": label, "variant": state}

	def clerk_name(yield_obj):
		clerk = getattr(yield_obj, "recorded_by", None)
		if clerk:
			full_name = clerk.get_full_name()
			return full_name or clerk.get_username()
		return "Unassigned"

	def storage_location_for(item):
		mapping = {
			"raw": "Raw Holding Bay",
			"atm": "Cold Room A",
			"esl": "Cold Room B",
			"yogurt": "Fermentation Chill Zone",
			"mala": "Fermentation Chill Zone",
			"ghee": "Ambient Store",
		}
		return mapping.get(item.product_category, "General Storage")

	all_yields = MilkYield.objects.select_related("cow")

	collection_qs = all_yields
	if filters["batch_type"]:
		collection_qs = collection_qs.filter(session=filters["batch_type"])
	if filters["tank"]:
		collection_qs = collection_qs.filter(storage_tank=filters["tank"])
	latest_collections = list(collection_qs.order_by("-recorded_at")[:20])

	collection_rows = []
	for entry in latest_collections:
		window_open = bool(
			entry.collection_window_start
			and entry.collection_window_end
			and entry.collection_window_start <= entry.recorded_at <= entry.collection_window_end
		)
		if not window_open:
			status = build_status("fail", "Batch closed — collection not allowed.")
		elif entry.quality_grade == "low":
			status = build_status("fail", "Low quality — hold sample.")
		elif entry.quality_grade == "premium":
			status = build_status("pass", "Ready for batching.")
		else:
			status = build_status("pending", "Awaiting batch assignment.")

		collection_rows.append(
			{
				"batch_id": entry.id,
				"session": entry.get_session_display(),
				"window_start": entry.collection_window_start,
				"window_end": entry.collection_window_end,
				"clerk": clerk_name(entry),
				"volume": entry.yield_litres,
				"status": status,
				"timestamp": entry.recorded_at,
			}
		)

	lab_tests_qs = BatchTest.objects.select_related("batch", "tested_by")
	if filters["batch_type"]:
		lab_tests_qs = lab_tests_qs.filter(batch__session=filters["batch_type"])
	if filters["tank"]:
		lab_tests_qs = lab_tests_qs.filter(batch__yields__storage_tank=filters["tank"]).distinct()
	lab_tests_qs = lab_tests_qs.order_by("-tested_at")
	lab_tests = list(lab_tests_qs[:20])

	lab_rows = []
	for test in lab_tests:
		if test.result == "approved":
			status = build_status("pass", "Pass")
		elif test.result == "rejected":
			status = build_status("fail", "Fail")
		else:
			status = build_status("pending", "Pending")

		lab_rows.append(
			{
				"batch_id": test.batch_id,
				"test_id": test.id,
				"fat_pct": test.fat_percentage,
				"snf_pct": test.snf_percentage,
				"acidity_pct": test.acidity,
				"contaminants": test.contaminants or "None",
				"session": test.batch.get_session_display(),
				"status": status,
				"tester": test.tested_by,
				"tested_at": test.tested_at,
			}
		)

	raw_totals = collection_qs.aggregate(total_litres=Sum("yield_litres"), total_samples=Count("id"))
	raw_summary = {
		"samples": raw_totals.get("total_samples") or 0,
		"litres": raw_totals.get("total_litres") or 0,
		"premium": collection_qs.filter(quality_grade="premium").count(),
		"standard": collection_qs.filter(quality_grade="standard").count(),
		"low": collection_qs.filter(quality_grade="low").count(),
	}

	batch_test_summary = {
		"tests": lab_tests_qs.count(),
		"approved": lab_tests_qs.filter(result="approved").count(),
		"pending": lab_tests_qs.filter(result="pending").count(),
		"rejected": lab_tests_qs.filter(result="rejected").count(),
	}

	production_qs = ProductionBatch.objects.select_related("lab_approval", "processed_by").order_by("-produced_at")
	if filters["tank"]:
		production_qs = production_qs.filter(source_tank=filters["tank"])
	if filters["product"]:
		production_qs = production_qs.filter(product_type=filters["product"])
	production_rows = []
	for batch in production_qs[:20]:
		lab_approval = getattr(batch, "lab_approval", None)
		if lab_approval and lab_approval.overall_result == "rejected":
			status = build_status("fail", "Rejected by lab")
		elif lab_approval and lab_approval.overall_result == "approved" and lab_approval.expiry_date:
			status = build_status("pass", "Ready for storage release")
		elif lab_approval and lab_approval.overall_result == "approved":
			status = build_status("pending", "Awaiting expiry issuance")
		elif batch.status == ProductionBatch.Status.PENDING_LAB:
			status = build_status("pending", "Pending lab testing")
		else:
			status = build_status("pending", "Lab review in progress")
		production_rows.append(
			{
				"production_id": batch.id,
				"tank": batch.source_tank,
				"product": batch.get_product_type_display(),
				"volume_used": batch.liters_used or batch.quantity_produced,
				"lab_test_id": lab_approval.id if lab_approval else None,
				"expiry_date": lab_approval.expiry_date if (lab_approval and lab_approval.expiry_date) else None,
				"status": status,
				"processed_by": batch.processed_by,
				"produced_at": batch.produced_at,
			}
		)

	storage_qs = InventoryItem.objects.filter(
		batch_id__isnull=False,
		expiry_date__isnull=False,
		current_quantity__gt=0,
	)
	if filters["product"]:
		storage_qs = storage_qs.filter(product_category=filters["product"])
	expiry_cutoff = None
	if filters["expiry_before"]:
		try:
			expiry_cutoff = datetime.strptime(filters["expiry_before"], "%Y-%m-%d").date()
		except ValueError:
			expiry_cutoff = None
	if expiry_cutoff:
		storage_qs = storage_qs.filter(expiry_date__lte=expiry_cutoff)
	storage_qs = storage_qs.order_by("expiry_date")

	storage_rows = []
	for item in storage_qs[:20]:
		if item.is_expired:
			status = build_status("fail", "Expired — block dispatch")
		elif item.is_near_expiry:
			status = build_status("pending", "Near expiry — prioritize dispatch")
		else:
			status = build_status("pass", "In cold storage")

		storage_rows.append(
			{
				"storage_id": item.id,
				"batch_id": item.batch_id,
				"product": item.name,
				"expiry_date": item.expiry_date,
				"quantity": item.current_quantity,
				"location": storage_location_for(item),
				"status": status,
				"last_restocked": item.last_restocked,
			}
		)

	production_totals = production_qs.aggregate(total_volume=Sum("quantity_produced"))
	production_summary = {
		"batches": production_qs.count(),
		"volume": production_totals.get("total_volume") or 0,
		"awaiting_lab": production_qs.filter(status=ProductionBatch.Status.PENDING_LAB).count(),
	}

	lab_summary = {
		"approvals": ProductionBatch.objects.filter(lab_approval__isnull=False).count(),
		"approved_with_expiry": ProductionBatch.objects.filter(
			lab_approval__overall_result="approved",
			lab_approval__expiry_date__isnull=False,
		).count(),
		"pending_expiry": ProductionBatch.objects.filter(
			lab_approval__overall_result="approved",
			lab_approval__expiry_date__isnull=True,
		).count(),
		"rejected": ProductionBatch.objects.filter(lab_approval__overall_result="rejected").count(),
	}

	store_summary = {
		"items": InventoryItem.objects.filter(batch_id__isnull=False).count(),
		"within_window": InventoryItem.objects.filter(batch_id__isnull=False, expiry_date__gt=today).count(),
		"expired": InventoryItem.objects.filter(batch_id__isnull=False, expiry_date__isnull=False, expiry_date__lte=today).count(),
	}

	overview = {
		"collections": MilkYield.objects.count(),
		"lab_tests": BatchTest.objects.count(),
		"approved_batches": BatchTest.objects.filter(result="approved").count(),
		"storage_batches": InventoryItem.objects.filter(batch_id__isnull=False, expiry_date__isnull=False).count(),
	}

	filter_options = {
		"batch_types": MilkYield.SESSION_CHOICES,
		"tanks": [tank for tank in MilkYield.TANK_CAPACITY_LITRES.keys() if tank not in ("Unassigned", "Spoilt Tank")],
		"products": ProductionBatch.PRODUCT_CHOICES,
	}

	return render(
		request,
		"lab/lab_dashboard.html",
		{
			"overview": overview,
			"filters": filters,
			"filter_options": filter_options,
			"collection_rows": collection_rows,
			"lab_rows": lab_rows,
			"production_rows": production_rows,
			"storage_rows": storage_rows,
			"raw_summary": raw_summary,
			"batch_test_summary": batch_test_summary,
			"session_windows": session_windows,
			"open_batches": open_batches,
			"closed_batches": closed_batches,
			"production_summary": production_summary,
			"lab_summary": lab_summary,
			"store_summary": store_summary,
		},
	)


@login_required
@permission_required("lab.change_batch", raise_exception=True)
def collection_session_admin(request):
	effective_windows = MilkYield.get_collection_windows(force_refresh=True)
	initial_rows = [
		{
			"session_key": window["key"],
			"start_time": window["start"],
			"end_time": window["end"],
		}
		for window in effective_windows
	]
	formset_prefix = "windows"
	if request.method == "POST" and request.POST.get("form_type") == "window":
		formset = SessionWindowFormSet(request.POST, prefix=formset_prefix)
		if formset.is_valid():
			default_map = {window["key"]: window for window in MilkYield.COLLECTION_WINDOWS}
			for form in formset:
				data = form.cleaned_data
				if not data:
					continue
				session_key = data["session_key"]
				start_time = data["start_time"]
				end_time = data["end_time"]
				defaults = default_map.get(session_key)
				if defaults and start_time == defaults["start"] and end_time == defaults["end"]:
					CollectionWindowOverride.objects.filter(session_key=session_key).delete()
					continue
				CollectionWindowOverride.objects.update_or_create(
					session_key=session_key,
					defaults={
						"start_time": start_time,
						"end_time": end_time,
						"updated_by": request.user,
					},
				)
			messages.success(request, "Collection windows updated successfully.")
			return redirect("lab:session_admin")
		else:
			messages.error(request, "Please fix the errors highlighted below.")
	else:
		formset = SessionWindowFormSet(initial=initial_rows, prefix=formset_prefix)

	date_param = request.GET.get("collection_date")
	try:
		selected_date = datetime.strptime(date_param, "%Y-%m-%d").date() if date_param else timezone.localdate()
	except ValueError:
		selected_date = timezone.localdate()

	session_cards = []
	for window in effective_windows:
		batch = Batch.for_session(window["key"], collection_date=selected_date, create=False)
		litres = batch.total_volume_litres() if batch else Decimal("0")
		session_cards.append(
			{
				"meta": window,
				"batch": batch,
				"state": batch.state if batch else Batch.State.OPEN,
				"is_open": batch.is_open if batch else True,
				"is_locked": batch.is_locked if batch else False,
				"batch_id": batch.id if batch else None,
				"litres": litres,
				"opened_at": batch.opened_at if batch else None,
				"closed_at": batch.closed_at if batch else None,
			}
		)

	window_rows = list(zip(formset.forms, effective_windows))
	return render(
		request,
		"lab/session_admin.html",
		{
			"formset": formset,
			"window_rows": window_rows,
			"session_cards": session_cards,
			"selected_date": selected_date,
		},
	)


@login_required
@permission_required("lab.change_batch", raise_exception=True)
def collection_session_toggle(request):
	if request.method != "POST":
		return redirect("lab:dashboard")
	session_key = request.POST.get("session")
	action = request.POST.get("action")
	target_date_raw = request.POST.get("collection_date")
	redirect_to = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("lab:dashboard")

	valid_sessions = {value for value, _ in MilkYield.SESSION_CHOICES}
	if session_key not in valid_sessions:
		messages.error(request, "Select a valid collection window before performing this action.")
		return redirect(redirect_to)

	try:
		target_date = datetime.strptime(target_date_raw, "%Y-%m-%d").date() if target_date_raw else timezone.now().date()
	except (TypeError, ValueError):
		target_date = timezone.now().date()

	batch = Batch.for_session(session_key, collection_date=target_date)
	try:
		if action == "open":
			batch.open(user=request.user)
			messages.success(request, f"{session_key.title()} batch reopened for {target_date:%b %d}.")
		elif action == "close":
			batch.close(user=request.user)
			messages.info(request, f"{session_key.title()} batch closed for {target_date:%b %d}.")
		else:
			messages.error(request, "Unknown batch action requested.")
	except ValidationError as exc:
		messages.error(request, str(exc))
	return redirect(redirect_to)
@login_required
@permission_required("lab.view_labbatchapproval", raise_exception=True)
def batch_approvals_index(request):
	filters = {
		"result": request.GET.get("result", ""),
		"tank": request.GET.get("tank", ""),
		"expiry_state": request.GET.get("expiry_state", ""),
	}
	assignable_tanks = [tank for tank in MilkYield.TANK_CAPACITY_LITRES.keys() if tank not in ("Unassigned", "Spoilt Tank")]

	if request.method == "POST" and request.POST.get("action") == "quick_test":
		if not request.user.has_perm("lab.add_batchtest"):
			messages.error(request, "You do not have permission to record lab tests from this screen.")
			return redirect("lab:batch_approvals")
		batch_id = request.POST.get("batch_id")
		batch = get_object_or_404(Batch.objects.prefetch_related("yields"), pk=batch_id)
		existing_test = getattr(batch, "test", None)
		if existing_test:
			messages.info(request, "This batch already has a recorded test. Open it to make edits.")
			return redirect("lab:batch_test_detail", existing_test.id)
		if batch.state == Batch.State.LOCKED:
			messages.error(request, "This batch is already locked. Open the test detail to review it instead.")
			return redirect("lab:batch_approvals")
		if batch.state == Batch.State.OPEN:
			try:
				batch.close(user=request.user)
			except ValidationError as exc:
				messages.error(request, str(exc))
				return redirect("lab:batch_approvals")
		selected_tank = (request.POST.get("storage_tank") or "").strip()
		if selected_tank not in assignable_tanks:
			messages.error(request, "Select a valid certified tank before saving the test.")
			return redirect("lab:batch_approvals")

		def current_batch_tank(obj):
			distinct = list(
				obj.yields.exclude(storage_tank__in=["", "Unassigned"])
				.values_list("storage_tank", flat=True)
				.distinct()
			)
			return distinct[0] if len(distinct) == 1 else ""

		form = BatchTestForm(request.POST)
		if not form.is_valid():
			errors = "; ".join([f"{field}: {', '.join(err_list)}" for field, err_list in form.errors.items()]) or "Please review the highlighted fields."
			messages.error(request, f"Unable to save batch test: {errors}")
			return redirect("lab:batch_approvals")

		current_tank = current_batch_tank(batch)
		if selected_tank != current_tank:
			batch.yields.update(storage_tank=selected_tank)
			messages.info(request, f"Batch storage tank updated to {selected_tank}.")

		test = form.save(commit=False)
		test.batch = batch
		if not getattr(test, "tested_by", None):
			test.tested_by = request.user
		test.save()
		if test.result == "approved":
			test.approve()
		elif test.result == "rejected":
			test.reject(reason=test.contaminants or None)
		if test.result in {"approved", "rejected"}:
			batch.lock()
		messages.success(request, f"Lab test recorded for batch {batch.id}.")
		return redirect("lab:batch_approvals")

	approvals_qs = (
		LabBatchApproval.objects.select_related("production_batch__processed_by", "approved_by")
		.order_by("-approved_at")
	)
	if filters["result"]:
		approvals_qs = approvals_qs.filter(overall_result=filters["result"])
	if filters["tank"]:
		approvals_qs = approvals_qs.filter(production_batch__source_tank=filters["tank"])
	if filters["expiry_state"] == "issued":
		approvals_qs = approvals_qs.filter(expiry_date__isnull=False)
	elif filters["expiry_state"] == "pending":
		approvals_qs = approvals_qs.filter(expiry_date__isnull=True)

	approvals = list(approvals_qs[:100])
	totals = {
		"total": LabBatchApproval.objects.count(),
		"approved": LabBatchApproval.objects.filter(overall_result="approved").count(),
		"pending": LabBatchApproval.objects.filter(overall_result="pending").count(),
		"rejected": LabBatchApproval.objects.filter(overall_result="rejected").count(),
		"with_expiry": LabBatchApproval.objects.filter(expiry_date__isnull=False).count(),
	}
	tank_options = sorted(set(ProductionBatch.objects.values_list("source_tank", flat=True)))

	unassigned_qs = (
		Batch.objects.filter(yields__storage_tank__in=["", "Unassigned"])
		.prefetch_related("yields__cow")
		.annotate(sample_count=Count("yields", distinct=True), total_litres=Sum("yields__yield_litres"))
		.order_by("-collection_date", "-created_at")
		.distinct()
	)[:10]
	unassigned_batches = []
	for pending_batch in unassigned_qs:
		distinct_tanks = list(
			pending_batch.yields.exclude(storage_tank__in=["", "Unassigned"])
			.values_list("storage_tank", flat=True)
			.distinct()
		)
		current_tank = distinct_tanks[0] if len(distinct_tanks) == 1 else ""
		unassigned_batches.append(
			{
				"batch": pending_batch,
				"current_tank": current_tank,
				"sample_count": pending_batch.sample_count or 0,
				"total_litres": pending_batch.total_litres or Decimal("0"),
			}
		)

	session_windows = (
		Batch.objects.select_related("opened_by", "closed_by", "test")
		.annotate(total_litres=Sum("yields__yield_litres"))
		.order_by("-collection_date", "-opened_at")
	)

	return render(
		request,
		"lab/batch_approvals.html",
		{
			"approvals": approvals,
			"filters": filters,
			"totals": totals,
			"tank_options": tank_options,
			"result_choices": LabBatchApproval.RESULT_CHOICES,
			"test_result_choices": BatchTest.RESULT_CHOICES,
			"unassigned_batches": unassigned_batches,
			"assignable_tanks": assignable_tanks,
			"session_windows": session_windows,
		},
	)


def _batch_list_filters_from_request(request):
	return {
		"session": request.GET.get("session", ""),
		"status": request.GET.get("status", ""),
	}


def _filtered_batch_queryset(filters):
	qs = (
		Batch.objects.select_related("test")
		.annotate(
			total_litres=Sum("yields__yield_litres"),
			sample_count=Count("yields", distinct=True),
		)
		.order_by("-created_at")
	)
	if filters["session"]:
		qs = qs.filter(session=filters["session"])
	if filters["status"]:
		status_val = filters["status"]
		if status_val == "pending":
			qs = qs.filter(Q(test__isnull=True) | Q(test__result="pending"))
		else:
			qs = qs.filter(test__result=status_val)
	return qs


def _batch_lab_status_label(batch):
	test = getattr(batch, "test", None)
	if test:
		return test.get_result_display()
	return "Pending"


@login_required
@permission_required("lab.view_batch", raise_exception=True)
def batch_list(request):
	filters = _batch_list_filters_from_request(request)
	batches_qs = _filtered_batch_queryset(filters)
	volume_totals = batches_qs.aggregate(total=Sum("yields__yield_litres"))
	batches = list(batches_qs[:50])
	stats = {
		"total": Batch.objects.count(),
		"tested": Batch.objects.filter(test__isnull=False).count(),
		"pending": Batch.objects.filter(Q(test__isnull=True) | Q(test__result="pending")).count(),
		"approved": Batch.objects.filter(test__result="approved").count(),
		"rejected": Batch.objects.filter(test__result="rejected").count(),
		"litres": volume_totals.get("total") or 0,
	}

	return render(
		request,
		"lab/batch_list.html",
		{
			"batches": batches,
			"filters": filters,
			"stats": stats,
			"session_choices": MilkYield.SESSION_CHOICES,
			"status_choices": BatchTest.RESULT_CHOICES,
		},
	)


@login_required
@permission_required("lab.change_batch", raise_exception=True)
def batch_edit(request, batch_id):
	batch = get_object_or_404(Batch, pk=batch_id)
	next_url = request.GET.get("next") or request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("lab:batch_approvals")
	if request.method == "POST":
		action = request.POST.get("action", "update")
		if action == "delete":
			batch_display = f"Batch #{batch.id}"
			batch.delete()
			messages.warning(request, f"{batch_display} deleted.")
			return redirect(next_url)
		form = BatchEditForm(request.POST, instance=batch)
		if form.is_valid():
			original_state = batch.state
			desired_state = form.cleaned_data["state"]
			update_fields = []
			if "session" in form.changed_data:
				batch.session = form.cleaned_data["session"]
				update_fields.append("session")
			if "collection_date" in form.changed_data:
				batch.collection_date = form.cleaned_data["collection_date"]
				update_fields.append("collection_date")
			if update_fields:
				batch.save(update_fields=update_fields)
			if desired_state != original_state:
				try:
					if desired_state == Batch.State.OPEN:
						batch.open(user=request.user)
					elif desired_state == Batch.State.CLOSED:
						batch.close(user=request.user)
					elif desired_state == Batch.State.LOCKED:
						batch.lock()
				except ValidationError as exc:
					messages.error(request, str(exc))
					return redirect(request.path)
			messages.success(request, "Batch updated successfully.")
			return redirect(next_url)
	else:
		form = BatchEditForm(instance=batch)
	return render(
		request,
		"lab/batch_edit.html",
		{
			"batch": batch,
			"form": form,
			"next": next_url,
		},
	)


@login_required
@permission_required("lab.view_batch", raise_exception=True)
def batch_list_export(request):
	filters = _batch_list_filters_from_request(request)
	export_format = (request.GET.get("format") or "xlsx").lower()
	batches = list(_filtered_batch_queryset(filters))
	if export_format == "pdf":
		return _export_batches_to_pdf(batches)
	return _export_batches_to_excel(batches)


def _export_batches_to_excel(batches):
	workbook = Workbook()
	sheet = workbook.active
	sheet.title = "Intake batches"
	headers = [
		"Batch ID",
		"Session",
		"Collection date",
		"State",
		"Samples",
		"Total litres",
		"Lab status",
	]
	sheet.append(headers)
	for batch in batches:
		collection_date = batch.collection_date.strftime("%Y-%m-%d") if batch.collection_date else ""
		sheet.append(
			[
				batch.id,
				batch.get_session_display(),
				collection_date,
				batch.state.title(),
				batch.sample_count or 0,
				batch.total_litres or Decimal("0"),
				_batch_lab_status_label(batch),
			]
		)
	response = HttpResponse(
		content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
	)
	response["Content-Disposition"] = "attachment; filename=intake_batches.xlsx"
	workbook.save(response)
	return response


def _export_batches_to_pdf(batches):
	response = HttpResponse(content_type="application/pdf")
	response["Content-Disposition"] = "attachment; filename=intake_batches.pdf"
	page_size = landscape(A4)
	pdf = canvas.Canvas(response, pagesize=page_size)
	width, height = page_size
	margin = inch * 0.5
	y_position = height - margin
	line_height = 16
	headers = [
		"Batch ID",
		"Session",
		"Collection date",
		"State",
		"Samples",
		"Litres",
		"Lab status",
	]
	column_positions = [margin, margin + 80, margin + 180, margin + 300, margin + 380, margin + 460, margin + 540]
	def draw_header(current_y):
		pdf.setFont("Helvetica-Bold", 10)
		for idx, label in enumerate(headers):
			pdf.drawString(column_positions[idx], current_y, label)
		pdf.setFont("Helvetica", 9)
		return current_y - line_height

	pdf.setFont("Helvetica-Bold", 14)
	pdf.drawString(margin, y_position, "Intake batches export")
	y_position -= line_height * 1.5
	y_position = draw_header(y_position)
	for batch in batches:
		if y_position < (margin + line_height):
			pdf.showPage()
			width, height = page_size
			y_position = height - margin
			y_position = draw_header(y_position)
		collection_date = batch.collection_date.strftime("%Y-%m-%d") if batch.collection_date else ""
		litres_value = batch.total_litres or Decimal("0")
		row_values = [
			f"#{batch.id}",
			batch.get_session_display(),
			collection_date,
			batch.state.title(),
			str(batch.sample_count or 0),
			f"{litres_value:.2f}",
			_batch_lab_status_label(batch),
		]
		for idx, value in enumerate(row_values):
			pdf.drawString(column_positions[idx], y_position, value)
		y_position -= line_height
	pdf.save()
	return response


@login_required
@permission_required("lab.add_batchtest", raise_exception=True)
def batch_test_run(request, batch_id):
	batch = get_object_or_404(Batch.objects.prefetch_related("yields__cow", "test"), pk=batch_id)
	instance = getattr(batch, "test", None)
	total_litres = batch.yields.aggregate(total=Sum("yield_litres"))["total"] or 0
	assignable_tanks = [tank for tank in MilkYield.TANK_CAPACITY_LITRES.keys() if tank != "Unassigned"]

	def resolve_current_tank():
		distinct = list(
			batch.yields.exclude(storage_tank__in=["", "Unassigned"])
			.values_list("storage_tank", flat=True)
			.distinct()
		)
		return distinct[0] if len(distinct) == 1 else ""

	current_tank = resolve_current_tank()
	selected_tank = None
	if batch.state == Batch.State.OPEN and instance is None:
		messages.error(request, "Close the batch before running a consolidated lab test.")
		return redirect("lab:batch_list")
	if batch.state == Batch.State.LOCKED and instance is None:
		messages.error(request, "This batch has already been locked by another tester.")
		return redirect("lab:batch_list")

	if request.method == "POST":
		selected_tank = request.POST.get("storage_tank") or None
		if selected_tank:
			if selected_tank not in assignable_tanks:
				messages.error(request, "Select a valid certified tank before saving the test.")
				return redirect("lab:batch_test_run", batch_id=batch.id)
			if selected_tank != current_tank:
				batch.yields.update(storage_tank=selected_tank)
				current_tank = selected_tank
				messages.success(request, f"Batch storage tank updated to {selected_tank}.")
		form = BatchTestForm(request.POST, instance=instance)
		if form.is_valid():
			test = form.save(commit=False)
			test.batch = batch
			if not getattr(test, "tested_by", None):
				test.tested_by = request.user
			test.save()
			if test.result == "approved":
				test.approve()
			elif test.result == "rejected":
				test.reject(reason=test.contaminants or None)
			if test.result in {"approved", "rejected"}:
				batch.lock()
			messages.success(request, "Batch test saved.")
			return redirect("lab:batch_test_detail", test.id)
	else:
		form = BatchTestForm(instance=instance)

	return render(
		request,
		"lab/batch_test_form.html",
		{
			"batch": batch,
			"form": form,
			"total_litres": total_litres,
			"tank_choices": assignable_tanks,
			"selected_tank": (selected_tank or current_tank),
			"current_tank": current_tank or "Unassigned",
		},
	)


@login_required
@permission_required("lab.view_batchtest", raise_exception=True)
def batch_test_detail(request, test_id):
	test = get_object_or_404(
		BatchTest.objects.select_related("batch", "tested_by").prefetch_related("batch__yields__cow"),
		pk=test_id,
	)
	batch = test.batch
	total_litres = batch.yields.aggregate(total=Sum("yield_litres"))["total"] or 0

	return render(
		request,
		"lab/batch_test_detail.html",
		{"test": test, "batch": batch, "total_litres": total_litres},
	)


@login_required
@permission_required("lab.view_batchtest", raise_exception=True)
def batch_tests_board(request):
	filters = {
		"status": request.GET.get("status", ""),
		"tank": request.GET.get("tank", ""),
		"product": request.GET.get("product", ""),
		"window": request.GET.get("window", ""),
	}

	if request.method == "POST":
		batch_id = request.POST.get("batch_id")
		storage_tank = request.POST.get("storage_tank")
		if not batch_id or not storage_tank:
			messages.error(request, "Select both a batch and a tank before assigning.")
			return redirect("lab:batch_tests")

		valid_tanks = [
			tank
			for tank in MilkYield.TANK_CAPACITY_LITRES.keys()
			if tank not in ("Unassigned", "Spoilt Tank")
		]
		if storage_tank not in valid_tanks:
			messages.error(request, "Choose an active certified tank.")
			return redirect("lab:batch_tests")

		batch = get_object_or_404(ProductionBatch, pk=batch_id)
		batch.source_tank = storage_tank
		batch.save(update_fields=["source_tank"])
		messages.success(request, f"Batch {batch_id} assigned to {storage_tank}.")
		return redirect("lab:batch_tests")

	closed_qs = (
		ProductionBatch.objects.select_related("processed_by", "lab_approval", "lab_approval__approved_by")
		.filter(status=ProductionBatch.Status.PENDING_LAB)
	)

	if filters["tank"]:
		closed_qs = closed_qs.filter(source_tank=filters["tank"])
	if filters["product"]:
		closed_qs = closed_qs.filter(product_type=filters["product"])
	if filters["status"]:
		status_value = filters["status"]
		if status_value == "pending":
			closed_qs = closed_qs.filter(Q(lab_approval__isnull=True) | Q(lab_approval__overall_result="pending"))
		else:
			closed_qs = closed_qs.filter(lab_approval__overall_result=status_value)
	if filters["window"]:
		try:
			window_date = datetime.strptime(filters["window"], "%Y-%m-%d").date()
			closed_qs = closed_qs.filter(produced_at__date=window_date)
		except ValueError:
			pass

	available_tanks = list(
		MilkYield.objects.exclude(storage_tank__in=["Unassigned", "Spoilt Tank"])
		.values_list("storage_tank", flat=True)
		.distinct()
	)

	closed_qs = closed_qs.order_by("produced_at")
	closed_batches = []
	choice_lookup = dict(LabBatchApproval.RESULT_CHOICES)
	for batch in closed_qs:
		approval = getattr(batch, "lab_approval", None)
		lab_state = approval.overall_result if approval else "pending"
		closed_batches.append(
			{
				"id": batch.id,
				"code": f"PB{batch.id}",
				"source_tank": batch.source_tank,
				"product_type": batch.product_type,
				"get_product_type_display": batch.get_product_type_display(),
				"sku": batch.sku,
				"quantity_produced": batch.quantity_produced,
				"closed_at": batch.produced_at,
				"processed_by": batch.processed_by,
				"lab_state": lab_state,
				"lab_state_label": choice_lookup.get(lab_state, lab_state.title()),
				"last_tested_at": approval.approved_at if approval else None,
				"last_tested_by": approval.approved_by.get_full_name() if approval and approval.approved_by else "",
				"test_url": reverse("lab:approve_batch", args=[batch.id]),
				"assign_url": reverse("lab:batch_tests"),
				"preferred_tank": batch.source_tank if batch.source_tank not in ("Unassigned", "Spoilt Tank") else "",
			}
		)

	stats = {
		"closed": closed_qs.count(),
		"awaiting_test": closed_qs.filter(Q(lab_approval__isnull=True) | Q(lab_approval__overall_result="pending")).count(),
		"assignable": len(available_tanks),
		"rejected": closed_qs.filter(lab_approval__overall_result="rejected").count(),
	}

	oldest_batch = closed_batches[0] if closed_batches else {}
	filter_options = {
		"statuses": LabBatchApproval.RESULT_CHOICES,
		"tanks": [tank for tank in MilkYield.TANK_CAPACITY_LITRES.keys() if tank not in ("Unassigned", "Spoilt Tank")],
		"products": ProductionBatch.PRODUCT_CHOICES,
	}

	return render(
		request,
		"lab/batch_tests.html",
		{
			"filters": filters,
			"filter_options": filter_options,
			"closed_batches": closed_batches,
			"available_tanks": available_tanks,
			"stats": stats,
			"oldest_batch": oldest_batch,
			"assignment_form": None,
			"assignment_form_action": reverse("lab:batch_tests"),
		},
	)


