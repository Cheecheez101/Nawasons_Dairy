from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from inventory.models import InventoryItem
from .models import Supplier, SupplierOrder
from .forms import DispatchForm

class SupplierOrderCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'suppliers.add_supplierorder'

    def get(self, request, item_id):
        item = get_object_or_404(InventoryItem, pk=item_id)
        suppliers = Supplier.objects.all()
        return render(request, 'suppliers/create_order.html', {
            'item': item,
            'suppliers': suppliers,
        })

    def post(self, request, item_id):
        item = get_object_or_404(InventoryItem, pk=item_id)
        supplier = get_object_or_404(Supplier, pk=request.POST.get('supplier_id'))
        SupplierOrder.objects.create(
            supplier=supplier,
            inventory_item=item,
            quantity=item.reorder_quantity or item.reorder_threshold,
            expected_delivery=request.POST.get('expected_delivery'),
        )
        return redirect('inventory:dashboard')

class SupplierOrderListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'suppliers.view_supplierorder'

    def get(self, request):
        orders = SupplierOrder.objects.select_related('supplier', 'inventory_item').order_by('-order_date')
        return render(request, 'suppliers/order_list.html', {'orders': orders})

class SupplierOrderUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'inventory.dispatch_product'

    def post(self, request, pk):
        order = get_object_or_404(SupplierOrder, pk=pk)
        form = DispatchForm(request.POST, instance=order)
        if form.is_valid():
            dispatch = form.save(commit=False)
            if dispatch.status == 'delivered':
                dispatch.inventory_item.current_quantity += dispatch.quantity
                dispatch.inventory_item.save(update_fields=['current_quantity'])
            dispatch.save()
        return redirect('suppliers:order_list')
