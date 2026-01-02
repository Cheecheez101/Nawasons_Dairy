from django import forms

from .models import Supplier, SupplierOrder


class DispatchForm(forms.ModelForm):
    class Meta:
        model = SupplierOrder
        fields = ['status']


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            'name',
            'contact_person',
            'phone',
            'email',
            'address',
            'lead_time_days',
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

