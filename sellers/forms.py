from django import forms
from .models import Seller, SellerTransaction
from inventory.models import InventoryItem
from storage.models import Packaging
from django.utils import timezone

class SellerForm(forms.ModelForm):
    class Meta:
        model = Seller
        fields = ['name', 'phone_number', 'location', 'seller_type']

class SellerTransactionForm(forms.ModelForm):
    class Meta:
        model = SellerTransaction
        # transaction_date is set automatically; don't expose it in the form
        fields = ['seller', 'product', 'packaging', 'quantity', 'status']

    seller = forms.ModelChoiceField(queryset=Seller.objects.all())
    product = forms.ModelChoiceField(queryset=InventoryItem.objects.all())
    packaging = forms.ModelChoiceField(queryset=Packaging.objects.all())
    quantity = forms.IntegerField(min_value=1)
    status = forms.ChoiceField(choices=SellerTransaction.STATUS_CHOICES)

    def save(self, commit=True):
        obj = super().save(commit=False)
        # ensure transaction_date is set to today when saving from the form
        if not obj.transaction_date:
            obj.transaction_date = timezone.now().date()
        if commit:
            obj.save()
        return obj
