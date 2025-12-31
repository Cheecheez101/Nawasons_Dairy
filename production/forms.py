from django import forms
from django.db.models import Sum
from inventory.models import InventoryItem
from .models import MilkYield, Cow, ProductPrice, ProductionBatch


class MilkYieldForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cow'].label_from_instance = lambda obj: f"{obj.name} ({obj.cow_id})"

    class Meta:
        model = MilkYield
        fields = [
            'cow',
            'session',
            'yield_litres',
            'quality_grade',
            'quality_notes',
        ]
        widgets = {
            'yield_litres': forms.NumberInput(attrs={'step': '0.1'}),
            'quality_notes': forms.Textarea(attrs={'rows': 2}),
        }


class CowForm(forms.ModelForm):
    class Meta:
        model = Cow
        fields = '__all__'
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'breed': forms.TextInput(attrs={'class': 'form-control'}),
            'age': forms.NumberInput(attrs={'class': 'form-control'}),
            'health_status': forms.TextInput(attrs={'class': 'form-control'}),
        }


class ProductPriceForm(forms.ModelForm):
    class Meta:
        model = ProductPrice
        fields = '__all__'
        widgets = {
            'inventory_item': forms.Select(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'effective_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assigned_qs = ProductPrice.objects.exclude(pk=self.instance.pk if self.instance.pk else None)
        assigned_ids = assigned_qs.values_list('inventory_item_id', flat=True)
        self.fields['inventory_item'].queryset = (
            InventoryItem.objects
            .exclude(id__in=assigned_ids)
            .order_by('name')
        )
        if self.instance.pk:
            self.fields['inventory_item'].initial = self.instance.inventory_item
            self.fields['inventory_item'].disabled = True


class ProductionBatchForm(forms.ModelForm):
    """
    Form for creating a production batch from tank milk.
    """
    class Meta:
        model = ProductionBatch
        fields = '__all__'
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'produced_at': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }
