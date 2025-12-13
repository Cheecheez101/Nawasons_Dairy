from django import forms
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
        fields = [
            'cow_id',
            'name',
            'breed',
            'date_of_birth',
            'health_status',
            'stall_location',
            'daily_capacity_litres',
            'is_active',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }


class ProductPriceForm(forms.ModelForm):
    class Meta:
        model = ProductPrice
        fields = ['inventory_item', 'price']
        widgets = {
            'price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
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
        fields = ['milk_source', 'product_type', 'sku', 'quantity_produced']
        widgets = {
            'quantity_produced': forms.NumberInput(attrs={'step': '0.1', 'min': '0'}),
        }
        labels = {
            'milk_source': "Source Tank (Milk Yield)",
        }
        help_texts = {
            'milk_source': "Select the milk yield (tank) to use as the source for this batch.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show milk yields that have raw milk approved and are not in Spoilt Tank
        self.fields['milk_source'].queryset = MilkYield.objects.filter(raw_test_approved=True).exclude(storage_tank='Spoilt Tank').order_by('recorded_at')
        # Populate SKU choices from current ProductPrice records
        sku_choices = [('', '--- Select SKU ---')] + [(pp.sku, f"{pp.product_name} ({pp.sku})") for pp in ProductPrice.objects.select_related('inventory_item').order_by('product_name')]
        self.fields['sku'] = forms.ChoiceField(choices=sku_choices, required=True)
        # If editing an existing batch, keep sku initial
        if self.instance and getattr(self.instance, 'sku', None):
            self.fields['sku'].initial = self.instance.sku
