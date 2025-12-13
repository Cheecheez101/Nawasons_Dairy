from django.shortcuts import render, redirect
from django.views import View
from django.forms import formset_factory
from .forms import SalesTransactionForm, SalesItemForm
from .models import SalesTransaction, SalesItem
from inventory.models import InventoryItem
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.utils import timezone
from production.models import ProductPrice
from customers.models import Customer, LoyaltyTier

class SalesDashboardView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.view_salestransaction'

    def get(self, request):
        transactions = SalesTransaction.objects.order_by('-created_at')[:20]
        return render(request, 'sales/dashboard.html', {'transactions': transactions})

class SalesCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.add_salestransaction'
    SalesItemFormSet = formset_factory(SalesItemForm, extra=1)

    def get(self, request):
        form = SalesTransactionForm()
        formset = self.SalesItemFormSet()
        return render(request, 'sales/create.html', {'form': form, 'formset': formset})

    def _resolve_price(self, inventory_item, request):
        product_price = ProductPrice.current_for_inventory(inventory_item)
        if product_price:
            return product_price.price
        messages.warning(
            request,
            f"No ProductPrice found for {inventory_item.name}. Falling back to inventory default price.",
        )
        return inventory_item.default_price

    def post(self, request):
        form = SalesTransactionForm(request.POST)
        formset = self.SalesItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            transaction = form.save()
            total = 0
            for item_form in formset:
                if item_form.cleaned_data:
                    inventory_item = item_form.cleaned_data['inventory_item']
                    quantity = item_form.cleaned_data['quantity']
                    price = self._resolve_price(inventory_item, request)
                    SalesItem.objects.create(
                        transaction=transaction,
                        inventory_item=inventory_item,
                        quantity=quantity,
                        price_per_unit=price,
                    )
                    inventory_item.current_quantity -= quantity
                    inventory_item.save(update_fields=['current_quantity'])
                    total += quantity * price
            transaction.total_amount = total
            transaction.save(update_fields=['total_amount'])
            if transaction.customer and total:
                points_earned = LoyaltyTier.points_for_amount(total)
                if points_earned:
                    customer = transaction.customer
                    customer.loyalty_points += points_earned
                    customer.save(update_fields=['loyalty_points'])
                    customer.loyalty_ledger.create(
                        points_change=points_earned,
                        balance_after=customer.loyalty_points,
                        reason=f"Purchase {transaction.transaction_id} ({total:.2f})"
                    )
            return redirect('sales:dashboard')
        return render(request, 'sales/create.html', {'form': form, 'formset': formset})

class SalesReceiptView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.view_salestransaction'

    def get(self, request, pk):
        transaction = SalesTransaction.objects.prefetch_related('items__inventory_item').get(pk=pk)
        return render(request, 'sales/receipt.html', {'transaction': transaction})
