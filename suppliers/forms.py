from django import forms
from .models import SupplierOrder

class DispatchForm(forms.ModelForm):
    class Meta:
        model = SupplierOrder
        fields = ['status']

