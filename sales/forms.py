from django import forms
from .models import SalesTransaction
from inventory.models import InventoryItem
from customers.models import Customer

class SalesItemForm(forms.Form):
    inventory_item = forms.ModelChoiceField(queryset=InventoryItem.objects.all())
    # Legacy quantity (units) kept for backwards compatibility
    quantity = forms.DecimalField(max_digits=10, decimal_places=2, required=False)
    cartons = forms.IntegerField(min_value=0, required=False, initial=0)
    loose_units = forms.IntegerField(min_value=0, required=False, initial=0)
    bulk_price_per_carton = forms.DecimalField(max_digits=10, decimal_places=2, required=False)

class SalesTransactionForm(forms.ModelForm):
    customer = forms.ModelChoiceField(queryset=Customer.objects.all(), required=False, help_text='Registered customers earn loyalty points automatically')
    class Meta:
        model = SalesTransaction
        fields = ['customer', 'walk_in_customer_name', 'customer_phone', 'payment_mode', 'payment_status', 'payment_reference']
