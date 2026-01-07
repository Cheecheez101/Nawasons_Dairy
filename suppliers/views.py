from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from inventory.models import InventoryItem

from .forms import DispatchForm, SupplierForm
from .models import Supplier, SupplierOrder


class SupplierManageView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'suppliers.view_supplier'
    template_name = 'suppliers/suppliers.html'

    def get(self, request):
        return self._render_page(request)

    def post(self, request):
        action = request.POST.get('action')

        if action == 'create':
            if not request.user.has_perm('suppliers.add_supplier'):
                messages.error(request, 'You do not have permission to add suppliers.')
                return redirect('suppliers:manage')
            form = SupplierForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Supplier created successfully.')
                return redirect('suppliers:manage')
            messages.error(request, 'Unable to create the supplier. Please review the form.')
            return self._render_page(request, create_form=form)

        if action == 'update':
            if not request.user.has_perm('suppliers.change_supplier'):
                messages.error(request, 'You do not have permission to edit suppliers.')
                return redirect('suppliers:manage')
            supplier = get_object_or_404(Supplier, pk=request.POST.get('supplier_id'))
            form = SupplierForm(request.POST, instance=supplier)
            if form.is_valid():
                form.save()
                messages.success(request, f'{supplier.name} updated successfully.')
            else:
                messages.error(request, f'Could not update {supplier.name}.')
            return redirect('suppliers:manage')

        if action == 'delete':
            if not request.user.has_perm('suppliers.delete_supplier'):
                messages.error(request, 'You do not have permission to remove suppliers.')
                return redirect('suppliers:manage')
            supplier = get_object_or_404(Supplier, pk=request.POST.get('supplier_id'))
            if SupplierOrder.objects.filter(supplier=supplier).exists():
                messages.error(request, f'{supplier.name} has linked orders and cannot be deleted.')
            else:
                supplier.delete()
                messages.success(request, f'{supplier.name} removed from directory.')
            return redirect('suppliers:manage')

        messages.error(request, 'Unsupported action for suppliers management.')
        return redirect('suppliers:manage')

    def _render_page(self, request, create_form=None):
        suppliers = Supplier.objects.order_by('name')
        
        # Apply filters
        search = request.GET.get('q', '').strip()
        if search:
            suppliers = suppliers.filter(
                Q(name__icontains=search) | Q(contact_person__icontains=search) | Q(phone__icontains=search)
            )
        
        max_lead_time = request.GET.get('max_lead_time', '').strip()
        if max_lead_time:
            try:
                suppliers = suppliers.filter(lead_time_days__lte=int(max_lead_time))
            except (ValueError, TypeError):
                pass
        
        context = {
            'suppliers': suppliers,
            'create_form': create_form or SupplierForm(),
        }
        return render(request, self.template_name, context)

class SupplierOrderCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'suppliers.add_supplierorder'

    def get(self, request, item_id):
        item = get_object_or_404(InventoryItem, pk=item_id)
        suppliers = Supplier.objects.order_by('name')
        context = self._build_order_context(item, suppliers)
        return render(request, 'suppliers/create_order.html', context)

    def post(self, request, item_id):
        item = get_object_or_404(InventoryItem, pk=item_id)
        suppliers = Supplier.objects.order_by('name')
        supplier = get_object_or_404(Supplier, pk=request.POST.get('supplier_id'))

        raw_quantity = (request.POST.get('quantity') or '').strip()
        try:
            quantity = int(raw_quantity)
        except (TypeError, ValueError):
            quantity = 0

        if quantity <= 0:
            messages.error(request, 'Please enter a quantity greater than zero.')
            context = self._build_order_context(item, suppliers, selected_supplier_id=supplier.id)
            context['quantity_value'] = raw_quantity
            context['expected_delivery_value'] = request.POST.get('expected_delivery') or ''
            return render(request, 'suppliers/create_order.html', context)

        expected_delivery = (request.POST.get('expected_delivery') or '').strip()
        if not expected_delivery:
            messages.error(request, 'Select the expected delivery date before creating an order.')
            context = self._build_order_context(
                item,
                suppliers,
                selected_supplier_id=supplier.id,
                quantity_value=raw_quantity or quantity,
            )
            context['expected_delivery_value'] = ''
            return render(request, 'suppliers/create_order.html', context)

        SupplierOrder.objects.create(
            supplier=supplier,
            inventory_item=item,
            quantity=quantity,
            expected_delivery=expected_delivery,
        )
        messages.success(request, f'Order placed with {supplier.name} for {quantity} units of {item.name}.')
        return redirect('suppliers:order_list')

    def _build_order_context(self, item, suppliers, **overrides):
        today = timezone.now().date()
        default_quantity = item.reorder_quantity or item.reorder_threshold or 1
        first_supplier = suppliers[0] if suppliers else None
        lead_days = getattr(first_supplier, 'lead_time_days', 7) or 7
        default_expected = (today + timedelta(days=lead_days)).isoformat() if suppliers else ''
        context = {
            'item': item,
            'suppliers': suppliers,
            'today': today,
            'default_quantity': default_quantity,
            'default_expected_delivery': default_expected,
        }
        context.update(overrides)
        return context

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
