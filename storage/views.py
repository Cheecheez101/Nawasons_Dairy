
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
import json
from .forms import ExpiredStockInventoryForm, ColdStorageInventoryForm, StorageLocationForm, PackagingForm
from .models import ColdStorageInventory, StorageLocation, Packaging, ExpiredStockInventory


# PDF/Excel export implementations
import io
import openpyxl
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

@login_required
def export_inventory_pdf(request):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40
    p.setFont("Helvetica-Bold", 14)
    p.drawString(40, y, "Expired Inventory Report")
    y -= 30
    p.setFont("Helvetica", 10)
    headers = ["Product", "Packaging", "Cartons", "Loose", "Expiry", "Removed"]
    for i, h in enumerate(headers):
        p.drawString(40 + i*90, y, h)
    y -= 20
    expired_lots = ExpiredStockInventory.objects.select_related('product', 'packaging')
    for lot in expired_lots:
        if y < 60:
            p.showPage()
            y = height - 40
        row = [
            getattr(lot.product, 'name', ''),
            f"{lot.packaging.pack_size_ml}ml x {lot.packaging.packets_per_carton}",
            str(lot.cartons),
            str(lot.loose_units),
            str(lot.expiry_date),
            lot.removed_at.strftime('%Y-%m-%d') if lot.removed_at else '',
        ]
        for i, val in enumerate(row):
            p.drawString(40 + i*90, y, val)
        y -= 18
    p.save()
    buffer.seek(0)
    return HttpResponse(buffer, content_type='application/pdf')

@login_required
def export_inventory_excel(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Expired Inventory"
    headers = ["Product", "Packaging", "Cartons", "Loose", "Expiry", "Removed"]
    ws.append(headers)
    expired_lots = ExpiredStockInventory.objects.select_related('product', 'packaging')
    for lot in expired_lots:
        ws.append([
            getattr(lot.product, 'name', ''),
            f"{lot.packaging.pack_size_ml}ml x {lot.packaging.packets_per_carton}",
            lot.cartons,
            lot.loose_units,
            str(lot.expiry_date),
            lot.removed_at.strftime('%Y-%m-%d') if lot.removed_at else '',
        ])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=expired_inventory.xlsx'
    wb.save(response)
    return response

# Move active inventory to expired inventory
@login_required
@permission_required('storage.change_coldstorageinventory', raise_exception=True)
@require_POST
def move_to_expired(request, pk):
    lot = get_object_or_404(ColdStorageInventory, pk=pk)
    from .models import move_to_expired as move_func
    move_func(lot, request.user)
    messages.success(request, f"Moved {lot.packaging.product.name} to expired inventory.")
    return redirect('storage:expired_inventory_dashboard')
@login_required
@permission_required('storage.delete_expiredstockinventory', raise_exception=True)
@require_POST
def expired_inventory_remove(request, pk):
    lot = get_object_or_404(ExpiredStockInventory, pk=pk)
    if not getattr(lot, 'sold', False):
        lot.delete()
        messages.success(request, 'Expired inventory removed.')
    else:
        messages.warning(request, 'Cannot remove: this lot is marked as sold.')
    return redirect('storage:expired_inventory_dashboard')

@login_required
@permission_required('storage.change_expiredstockinventory', raise_exception=True)
def expired_inventory_edit(request, pk):
    lot = get_object_or_404(ExpiredStockInventory, pk=pk)
    if request.method == 'POST':
        form = ExpiredStockInventoryForm(request.POST, instance=lot)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expired inventory updated.')
            return redirect('storage:expired_inventory_dashboard')
    else:
        form = ExpiredStockInventoryForm(instance=lot)
    return render(request, 'storage/storage_inventory_form.html', {'form': form, 'title': 'Edit expired inventory', 'lot': lot})
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date

from .forms import ColdStorageInventoryForm, StorageLocationForm, PackagingForm
from .models import ColdStorageInventory, StorageLocation, Packaging, ExpiredStockInventory
import json


@login_required
@permission_required('storage.view_coldstorageinventory', raise_exception=True)
def storage_list(request):
    """Render the filtered cold storage inventory table."""
    inventory_qs = ColdStorageInventory.objects.select_related('production_batch', 'location')

    product_query = request.GET.get('product', '').strip()
    if product_query:
        inventory_qs = inventory_qs.filter(
            packaging__product__name__icontains=product_query
        )

    location_query = request.GET.get('location', '').strip()
    if location_query:
        inventory_qs = inventory_qs.filter(location__name__icontains=location_query)

    expiry_query = request.GET.get('expiry', '').strip()
    if expiry_query:
        parsed_expiry = parse_date(expiry_query)
        if parsed_expiry:
            inventory_qs = inventory_qs.filter(expiry_date=parsed_expiry)

    active_filters = {
        'product': product_query,
        'location': location_query,
        'expiry': expiry_query,
    }

    context = {
        'inventory': inventory_qs.order_by('expiry_date'),
        'active_filters': active_filters,
        'applied_filter_count': sum(1 for value in active_filters.values() if value),
    }
    return render(request, 'storage/storage_list.html', context)


@login_required
@permission_required('storage.view_packaging', raise_exception=True)
def packaging_list(request):
    """Show all packaging rules"""
    packages = Packaging.objects.select_related('product').all()
    # augment with a human-readable total units example for display
    packages_display = []
    for p in packages:
        example_cartons = 1
        total_units = example_cartons * p.packets_per_carton
        packages_display.append({'pkg': p, 'example_cartons': example_cartons, 'total_units': total_units})
    return render(request, 'storage/packaging_list.html', {'packages': packages_display})


@login_required
@permission_required('storage.view_packaging', raise_exception=True)
def packaging_detail(request, pk):
    pkg = get_object_or_404(Packaging, pk=pk)
    return render(request, 'storage/packaging_detail.html', {'package': pkg})


@login_required
@permission_required('storage.add_packaging', raise_exception=True)
def packaging_create(request):
    if request.method == 'POST':
        form = PackagingForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Packaging rule created.')
            return redirect('storage:packaging_list')
    else:
        form = PackagingForm()
    return render(request, 'storage/packaging_form.html', {'form': form})


@login_required
@permission_required('storage.change_packaging', raise_exception=True)
def packaging_edit(request, pk):
    pkg = get_object_or_404(Packaging, pk=pk)
    if request.method == 'POST':
        form = PackagingForm(request.POST, instance=pkg)
        if form.is_valid():
            form.save()
            messages.success(request, 'Packaging rule updated.')
            return redirect('storage:packaging_list')
    else:
        form = PackagingForm(instance=pkg)
    return render(request, 'storage/packaging_form.html', {'form': form, 'package': pkg})


@login_required
@permission_required('storage.view_storagelocation', raise_exception=True)
def storage_locations(request):
    """List all registered storage areas for admins to review/manage."""
    locations = StorageLocation.objects.order_by('name')
    return render(request, 'storage/storage_locations.html', {'locations': locations})


@login_required
@permission_required('storage.add_coldstorageinventory', raise_exception=True)
def inventory_add(request):
    form = ColdStorageInventoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Storage record created successfully.')
        return redirect('storage:storage_list')

    # packaging_map used by front-end JS: {packaging_id: packets_per_carton}
    packaging_map = {str(p.id): p.packets_per_carton for p in Packaging.objects.all()}

    return render(
        request,
        'storage/storage_inventory_form.html',
        {
            'form': form,
            'title': 'Add cold storage record',
            'packaging_map_json': json.dumps(packaging_map),
        },
    )


@login_required
@permission_required('storage.delete_coldstorageinventory', raise_exception=True)
def inventory_delete(request, pk):
    lot = get_object_or_404(ColdStorageInventory, pk=pk)
    if request.method == 'POST':
        lot.delete()
        messages.success(request, 'Storage record deleted successfully.')
        return redirect('storage:storage_list')

    return render(
        request,
        'storage/storage_inventory_confirm_delete.html',
        {
            'lot': lot,
        },
    )


@login_required
@permission_required('storage.change_coldstorageinventory', raise_exception=True)
def inventory_edit(request, pk):
    lot = get_object_or_404(ColdStorageInventory, pk=pk)
    form = ColdStorageInventoryForm(request.POST or None, instance=lot)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Storage record updated successfully.')
        return redirect('storage:storage_list')

    packaging_map = {str(p.id): p.packets_per_carton for p in Packaging.objects.all()}

    # Provide debug info so editors can see the source values used to prefill
    debug_batch = None
    try:
        pb = getattr(lot, 'production_batch', None)
        if pb:
            debug_batch = {
                'batch_id': pb.id,
                'sku': getattr(pb, 'sku', None),
                'quantity_produced': str(getattr(pb, 'quantity_produced', None)),
                'liters_used': str(getattr(pb, 'liters_used', None)),
            }
    except Exception:
        debug_batch = None

    return render(
        request,
        'storage/storage_inventory_form.html',
        {
            'form': form,
            'title': 'Edit cold storage record',
            'lot': lot,
            'packaging_map_json': json.dumps(packaging_map),
            'debug_batch': debug_batch,
            'lot_total_units': lot.total_units(),
        },
    )


@login_required
@permission_required('storage.add_storagelocation', raise_exception=True)
def location_add(request):
    form = StorageLocationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Storage area created successfully.')
        return redirect('storage:storage_locations')

    return render(
        request,
        'storage/storage_location_form.html',
        {
            'form': form,
            'title': 'Add storage area',
        },
    )


@login_required
@permission_required('storage.change_storagelocation', raise_exception=True)
def location_edit(request, pk):
    location = get_object_or_404(StorageLocation, pk=pk)
    form = StorageLocationForm(request.POST or None, instance=location)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Storage area updated successfully.')
        return redirect('storage:storage_locations')

    return render(
        request,
        'storage/storage_location_form.html',
        {
            'form': form,
            'title': 'Edit storage area',
            'location': location,
        },
    )


@login_required
@permission_required('storage.delete_storagelocation', raise_exception=True)
def location_delete(request, pk):
    location = get_object_or_404(StorageLocation, pk=pk)
    if request.method == 'POST':
        location.delete()
        messages.success(request, 'Storage area deleted successfully.')
        return redirect('storage:storage_locations')

    return render(
        request,
        'storage/storage_location_confirm_delete.html',
        {
            'location': location,
        },
    )


@login_required
@permission_required('storage.view_coldstorageinventory', raise_exception=True)
def expired_inventory_dashboard(request):
    active_lots = ColdStorageInventory.objects.exclude(status='expired').select_related('packaging')
    expired_lots = ExpiredStockInventory.objects.select_related('product', 'packaging')
    # Annotate with 'sold' status if not present
    for lot in expired_lots:
        if not hasattr(lot, 'sold'):
            lot.sold = False  # Default, update as needed
    return render(request, 'storage/expired_inventory_dashboard.html', {
        'active_lots': active_lots,
        'expired_lots': expired_lots,
    })
