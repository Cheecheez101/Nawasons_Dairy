from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date

from .forms import ColdStorageInventoryForm, StorageLocationForm
from .models import ColdStorageInventory, StorageLocation


@login_required
@permission_required('storage.view_coldstorageinventory', raise_exception=True)
def storage_list(request):
    """Render the filtered cold storage inventory table."""
    inventory_qs = ColdStorageInventory.objects.select_related('production_batch', 'location')

    product_query = request.GET.get('product', '').strip()
    if product_query:
        inventory_qs = inventory_qs.filter(product__icontains=product_query)

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

    return render(
        request,
        'storage/storage_inventory_form.html',
        {
            'form': form,
            'title': 'Add cold storage record',
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

    return render(
        request,
        'storage/storage_inventory_form.html',
        {
            'form': form,
            'title': 'Edit cold storage record',
            'lot': lot,
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
