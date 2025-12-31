from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from production.models import MilkYield, ProductionBatch
from django.db.models import Sum, Count
from .forms import RawMilkTestForm, TankBatchTestForm, LabBatchApprovalForm
from .models import TankBatchTest
from django.core.exceptions import PermissionDenied


@login_required
@permission_required("lab.add_rawmilktest", raise_exception=True)
def add_raw_test(request, yield_id):
    milk_yield = get_object_or_404(MilkYield, id=yield_id)
    if request.method == "POST":
        form = RawMilkTestForm(request.POST)
        if form.is_valid():
            test = form.save(commit=False)
            test.tested_by = request.user
            test.milk_yield = milk_yield
            try:
                # If lab approved and storage_tank provided, assign it
                if test.result == 'approved':
                    tank = form.cleaned_data.get('storage_tank')
                    if tank:
                        milk_yield.storage_tank = tank
                        milk_yield.save(update_fields=['storage_tank'])
                elif test.result == 'rejected':
                    milk_yield.storage_tank = 'Spoilt Tank'
                    milk_yield.raw_test_approved = False
                    milk_yield.save(update_fields=['storage_tank', 'raw_test_approved'])

                test.save()
                messages.success(request, "Raw milk test recorded successfully.")
                return redirect("lab:milk_yield_tests", yield_id=milk_yield.id)
            except Exception as e:
                form.add_error(None, str(e))
    else:
        form = RawMilkTestForm(initial={"milk_yield": milk_yield})
    return render(request, "lab/add_test.html", {"form": form, "milk_yield": milk_yield})


@login_required
@permission_required("lab.add_tankbatchtest", raise_exception=True)
def add_tank_test(request, yield_id):
    milk_yield = get_object_or_404(MilkYield, id=yield_id)
    if request.method == "POST":
        form = TankBatchTestForm(request.POST)
        if form.is_valid():
            test = form.save(commit=False)
            test.tested_by = request.user
            test.milk_yield = milk_yield
            test.save()
            messages.success(request, "Tank batch test recorded successfully.")
            return redirect("lab:milk_yield_tests", yield_id=milk_yield.id)
    else:
        form = TankBatchTestForm(initial={"milk_yield": milk_yield})
    return render(request, "lab/add_test.html", {"form": form, "milk_yield": milk_yield})


@login_required
@permission_required("lab.add_labbatchapproval", raise_exception=True)
def approve_batch(request, batch_id):
    batch = get_object_or_404(ProductionBatch, id=batch_id)
    approval = getattr(batch, "lab_approval", None)

    if request.method == "POST":
        form = LabBatchApprovalForm(request.POST, instance=approval)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.production_batch = batch
            obj.approved_by = request.user

            shelf_days = form.cleaned_data.get("shelf_life_days") or 0
            if obj.overall_result == "approved" and not obj.expiry_date and shelf_days:
                obj.set_expiry(shelf_life_days=shelf_days)
            else:
                obj.save()

            messages.success(request, "Batch approval saved.")
            return redirect("lab:tank_yield_tests", tank=batch.source_tank)
    else:
        form = LabBatchApprovalForm(instance=approval, initial={"production_batch": batch})
    return render(request, "lab/approve_batch.html", {"form": form, "batch": batch})


@login_required
@permission_required("lab.view_rawmilktest", raise_exception=True)
def milk_yield_tests(request, yield_id=None, cow_id=None, tank=None):
    """
    View milk yield tests for a specific yield, or all yields for a cow, or all yields for a tank.
    """
    if cow_id:
        # Show all yields/tests for this cow
        yields = MilkYield.objects.filter(cow_id=cow_id).select_related('cow')
        context = {
            'yields': yields,
            'cow': yields[0].cow if yields else None,
            'mode': 'cow',
        }
        return render(request, "lab/cow_yield_tests.html", context)
    elif tank:
        # Show all yields/tests for this tank
        yields = MilkYield.objects.filter(storage_tank=tank).select_related('cow')
        batches = ProductionBatch.objects.filter(source_tank=tank).select_related('processed_by')

        # Filtering batches
        product_type = request.GET.get('product_type')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        approval_status = request.GET.get('approval_status')

        if product_type:
            batches = batches.filter(product_type=product_type)
        if date_from:
            batches = batches.filter(produced_at__date__gte=date_from)
        if date_to:
            batches = batches.filter(produced_at__date__lte=date_to)
        if approval_status:
            if approval_status == 'approved':
                batches = batches.filter(lab_approval__overall_result='approved')
            elif approval_status == 'rejected':
                batches = batches.filter(lab_approval__overall_result='rejected')
            elif approval_status == 'pending':
                batches = batches.filter(lab_approval__isnull=True)

        # Get unique product types for filter
        product_types = ProductionBatch.objects.values_list('product_type', flat=True).distinct()

        context = {
            'yields': yields,
            'batches': batches,
            'tank': tank,
            'mode': 'tank',
            'product_types': product_types,
            'filters': {
                'product_type': product_type,
                'date_from': date_from,
                'date_to': date_to,
                'approval_status': approval_status,
            }
        }

        # Handle "Create Production Batch" form POST
        if request.method == 'POST' and request.POST.get('create_batch'):
            product_type_val = request.POST.get('product_type') or ''
            sku_val = request.POST.get('sku') or ''
            qty_val = request.POST.get('quantity_produced') or 0
            moved_to_lab_flag = True if request.POST.get('moved_to_lab') == 'on' else False
            try:
                batch = ProductionBatch(
                    source_tank=tank,
                    product_type=product_type_val,
                    sku=sku_val,
                    quantity_produced=qty_val,
                    processed_by=request.user
                )
                # if model has moved_to_lab attribute, set it
                if hasattr(batch, 'moved_to_lab'):
                    batch.moved_to_lab = moved_to_lab_flag
                batch.save()
                messages.success(request, "Production batch created.")
                return redirect('lab:tank_yield_tests', tank=tank)
            except Exception as e:
                messages.error(request, f"Could not create batch: {e}")

        # Compute size and units_produced for each batch
        for batch in batches:
            # compute size from sku suffix after last '-' (fallback to 1 on error)
            try:
                size = int(str(batch.sku).split("-")[-1])
                if size <= 0:
                    size = 1
            except Exception:
                size = 1
            batch.size = size

            # compute units produced as (litres * 1000) / size
            try:
                units = (float(batch.quantity_produced) * 1000.0) / size
                batch.units_produced = int(units)
            except Exception:
                batch.units_produced = 0

        return render(request, "lab/tank_yield_tests.html", context)
    else:
        milk_yield = get_object_or_404(MilkYield, id=yield_id)
        raw_tests = getattr(milk_yield, "raw_test", None)
        tank_tests = milk_yield.tank_tests.all().order_by("-tested_at")
        return render(
            request,
            "lab/milk_yield_tests.html",
            {"milk_yield": milk_yield, "raw_tests": raw_tests, "tank_tests": tank_tests},
        )

@login_required
@permission_required("lab.view_rawmilktest", raise_exception=True)
def lab_dashboard(request):
    yields = MilkYield.objects.select_related("cow")

    # Filtering
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    tank = request.GET.get('tank')
    status = request.GET.get('status')

    if date_from:
        yields = yields.filter(recorded_at__date__gte=date_from)
    if date_to:
        yields = yields.filter(recorded_at__date__lte=date_to)
    if tank:
        yields = yields.filter(storage_tank=tank)
    if status:
        if status == 'approved':
            yields = yields.filter(raw_test_approved=True)
        elif status == 'pending':
            yields = yields.filter(raw_test_approved=False)
        elif status == 'expired':
            yields = yields.filter(is_expired=True)
        elif status == 'near_expiry':
            yields = yields.filter(is_near_expiry=True)

    pending_approvals = ProductionBatch.objects.filter(lab_approval__isnull=True).count()
    near_expiry = sum(1 for y in yields if getattr(y, "is_near_expiry", False))

    # Tank-level tests: show recent tank batch tests for lab users
    tank_tests = TankBatchTest.objects.select_related('milk_yield', 'tested_by').order_by('-tested_at')[:50]

    # Approved tanks available for production
    approved_tanks = MilkYield.objects.filter(raw_test_approved=True).exclude(storage_tank='Spoilt Tank')

    # Tanks summary: show total litres available per tank (exclude Unassigned and Spoilt Tank)
    tanks_summary = (
        MilkYield.objects
        .exclude(storage_tank__in=['Unassigned', 'Spoilt Tank'])
        .values('storage_tank')
        .annotate(total_litres=Sum('yield_litres'), yields_count=Count('id'))
        .order_by('storage_tank')
    )

    # Get unique tanks for filter
    tanks = MilkYield.objects.values_list('storage_tank', flat=True).distinct().exclude(storage_tank__in=['Unassigned', 'Spoilt Tank'])

    # Get pending batches for approval
    pending_batches = ProductionBatch.objects.filter(lab_approval__isnull=True).select_related('processed_by')

    return render(request, "lab/lab_dashboard.html", {
        "yields": yields,
        "pending_approvals": pending_approvals,
        "near_expiry": near_expiry,
        "tank_tests": tank_tests,
        "approved_tanks": approved_tanks,
        "tanks_summary": tanks_summary,
        "tanks": tanks,
        "pending_batches": pending_batches,
        "filters": {
            'date_from': date_from,
            'date_to': date_to,
            'tank': tank,
            'status': status,
        }
    })


@login_required
@permission_required("lab.change_tankbatchtest", raise_exception=True)
def approve_tank_test(request, test_id, action):
    """Approve or reject a TankBatchTest identified by test_id.

    action is 'approve' or 'reject'. On approve we set the test and milk_yield status accordingly.
    """
    test = get_object_or_404(TankBatchTest, id=test_id)
    if action not in ("approve", "reject"):
        raise PermissionDenied("Invalid action")

    if request.method == 'POST' or request.method == 'GET':
        if action == 'approve':
            test.result = 'approved'
            test.tested_by = request.user
            test.save()
            # update all milk yields in the tank to approved
            MilkYield.objects.filter(storage_tank=test.milk_yield.storage_tank).update(tank_test_latest_status='approved')
            messages.success(request, f"Tank test {test.id} approved. Tank {test.milk_yield.storage_tank} is now approved for production.")
        else:
            test.result = 'rejected'
            test.tested_by = request.user
            test.save()
            # move all yields in the tank to spoilt tank and set status to rejected
            MilkYield.objects.filter(storage_tank=test.milk_yield.storage_tank).update(
                tank_test_latest_status='rejected',
                storage_tank='Spoilt Tank'
            )
            messages.success(request, f"Tank test {test.id} rejected. All milk in tank {test.milk_yield.storage_tank} moved to Spoilt Tank.")
    return redirect('lab:dashboard')


@login_required
@permission_required("lab.add_tankbatchtest", raise_exception=True)
def create_tank_test(request, tank):
    """Show yields in the specified tank and let lab create a TankBatchTest for a selected yield."""
    yields = MilkYield.objects.filter(storage_tank=tank).select_related('cow')
    total_litres = sum([y.yield_litres for y in yields])

    if request.method == 'POST':
        # Expect a yield_id and result from the form
        yield_id = request.POST.get('yield_id')
        result = request.POST.get('result')
        notes = request.POST.get('notes', '')
        if not yield_id or not result:
            messages.error(request, 'Select a source yield and a result.')
            return render(request, 'lab/create_tank_test.html', {'yields': yields, 'tank': tank, 'total_litres': total_litres})
        milk_yield = get_object_or_404(MilkYield, id=yield_id)
        test = TankBatchTest(milk_yield=milk_yield, result=result, notes=notes, tested_by=request.user)
        test.save()
        messages.success(request, 'Tank test created.')
        return redirect('lab:dashboard')

    return render(request, 'lab/create_tank_test.html', {'yields': yields, 'tank': tank, 'total_litres': total_litres})

@login_required
@permission_required("lab.view_rawmilktest", raise_exception=True)
def milk_yield_tests(request, yield_id=None, cow_id=None, tank=None):
    """
    View milk yield tests for a specific yield, or all yields for a cow, or all yields for a tank.
    """
    if cow_id:
        # Show all yields/tests for this cow
        yields = MilkYield.objects.filter(cow_id=cow_id).select_related('cow')
        context = {
            'yields': yields,
            'cow': yields[0].cow if yields else None,
            'mode': 'cow',
        }
        return render(request, "lab/cow_yield_tests.html", context)
    elif tank:
        # Show all yields/tests for this tank
        yields = MilkYield.objects.filter(storage_tank=tank).select_related('cow')
        batches = ProductionBatch.objects.filter(source_tank=tank).select_related('processed_by')

        # Filtering batches
        product_type = request.GET.get('product_type')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        approval_status = request.GET.get('approval_status')

        if product_type:
            batches = batches.filter(product_type=product_type)
        if date_from:
            batches = batches.filter(produced_at__date__gte=date_from)
        if date_to:
            batches = batches.filter(produced_at__date__lte=date_to)
        if approval_status:
            if approval_status == 'approved':
                batches = batches.filter(lab_approval__overall_result='approved')
            elif approval_status == 'rejected':
                batches = batches.filter(lab_approval__overall_result='rejected')
            elif approval_status == 'pending':
                batches = batches.filter(lab_approval__isnull=True)

        # Get unique product types for filter
        product_types = ProductionBatch.objects.values_list('product_type', flat=True).distinct()

        context = {
            'yields': yields,
            'batches': batches,
            'tank': tank,
            'mode': 'tank',
            'product_types': product_types,
            'filters': {
                'product_type': product_type,
                'date_from': date_from,
                'date_to': date_to,
                'approval_status': approval_status,
            }
        }

        # Handle "Create Production Batch" form POST
        if request.method == 'POST' and request.POST.get('create_batch'):
            product_type_val = request.POST.get('product_type') or ''
            sku_val = request.POST.get('sku') or ''
            qty_val = request.POST.get('quantity_produced') or 0
            moved_to_lab_flag = True if request.POST.get('moved_to_lab') == 'on' else False
            try:
                batch = ProductionBatch(
                    source_tank=tank,
                    product_type=product_type_val,
                    sku=sku_val,
                    quantity_produced=qty_val,
                    processed_by=request.user
                )
                # if model has moved_to_lab attribute, set it
                if hasattr(batch, 'moved_to_lab'):
                    batch.moved_to_lab = moved_to_lab_flag
                batch.save()
                messages.success(request, "Production batch created.")
                return redirect('lab:tank_yield_tests', tank=tank)
            except Exception as e:
                messages.error(request, f"Could not create batch: {e}")

        # Compute size and units_produced for each batch
        for batch in batches:
            # compute size from sku suffix after last '-' (fallback to 1 on error)
            try:
                size = int(str(batch.sku).split("-")[-1])
                if size <= 0:
                    size = 1
            except Exception:
                size = 1
            batch.size = size

            # compute units produced as (litres * 1000) / size
            try:
                units = (float(batch.quantity_produced) * 1000.0) / size
                batch.units_produced = int(units)
            except Exception:
                batch.units_produced = 0

        return render(request, "lab/tank_yield_tests.html", context)
    else:
        milk_yield = get_object_or_404(MilkYield, id=yield_id)
        raw_tests = getattr(milk_yield, "raw_test", None)
        tank_tests = milk_yield.tank_tests.all().order_by("-tested_at")
        return render(
            request,
            "lab/milk_yield_tests.html",
            {"milk_yield": milk_yield, "raw_tests": raw_tests, "tank_tests": tank_tests},
        )
