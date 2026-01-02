from decimal import Decimal

from django import forms
from django.utils import timezone
from inventory.models import InventoryItem
from .models import MilkYield, Cow, ProductPrice, ProductionBatch


class MilkYieldForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cow'].label_from_instance = lambda obj: f"{obj.name} ({obj.cow_id})"
        session_field = self.fields['session']
        session_field.help_text = "Automatically aligns with the current collection window."

        if self.instance and self.instance.pk:
            session_field.initial = self.instance.session
        else:
            current_session = MilkYield.resolve_collection_session(timezone.now())
            if current_session:
                session_field.initial = current_session
                session_label = dict(MilkYield.SESSION_CHOICES).get(current_session, current_session.title())
                session_field.help_text = f"{session_label} window auto-selected."
            else:
                session_field.initial = None
                session_field.help_text = (
                    "Collection is closed until the next intake window (00:00-06:00, 12:00-15:00, 16:00-19:00)."
                )

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

    def clean(self):
        cleaned_data = super().clean()

        if self.instance and self.instance.pk:
            return cleaned_data

        now = timezone.now()
        session_key = MilkYield.resolve_collection_session(now)
        if session_key:
            cleaned_data['session'] = session_key
            self.instance.session = session_key
            return cleaned_data

        requested_session = cleaned_data.get('session') or self.data.get('session')
        if requested_session and MilkYield.is_session_available(requested_session, now):
            cleaned_data['session'] = requested_session
            self.instance.session = requested_session
            return cleaned_data

        raise forms.ValidationError(
            "Milk intake is closed right now. Request the lab team to reopen the target batch window before recording more yields."
        )


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
        exclude = ['processed_by', 'moved_to_lab', 'produced_at', 'status']
        widgets = {
            'source_tank': forms.Select(attrs={'class': 'form-control'}),
            'product_type': forms.Select(attrs={'class': 'form-control'}),
            'sku': forms.Select(attrs={'class': 'form-control'}),
            'quantity_produced': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
            'liters_used': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate SKU choices from InventoryItem
        items = InventoryItem.objects.all().order_by('name')
        self.fields['sku'].widget = forms.Select(attrs={'class': 'form-control'})
        self.fields['sku'].choices = [('', '---------')] + [
            (item.sku, f"{item.name} ({item.sku})") for item in items
        ]
        self.fields['quantity_produced'].help_text = "Enter units produced. Leave blank to auto-calculate from litres."
        self.fields['liters_used'].help_text = "Enter litres consumed. Leave blank to auto-calculate from units."

    def clean(self):
        cleaned_data = super().clean()
        quantity = cleaned_data.get('quantity_produced')
        liters = cleaned_data.get('liters_used')
        sku = cleaned_data.get('sku')

        quantity = quantity if quantity not in (None, '') else None
        liters = liters if liters not in (None, '') else None

        if (not quantity or quantity <= 0) and (not liters or liters <= 0):
            raise forms.ValidationError("Provide either Quantity Produced or Liters Used with a value greater than zero.")

        if quantity is not None and quantity <= 0:
            self.add_error('quantity_produced', 'Quantity must be greater than zero.')
            quantity = None

        if liters is not None and liters <= 0:
            self.add_error('liters_used', 'Liters must be greater than zero.')
            liters = None

        if not sku:
            raise forms.ValidationError("Select a SKU to determine the conversion between units and litres.")

        try:
            item = InventoryItem.objects.get(sku=sku)
        except InventoryItem.DoesNotExist:
            raise forms.ValidationError("Selected SKU could not be found.")

        if not item.size_ml:
            raise forms.ValidationError("Selected SKU does not have a configured size (ml), so conversions cannot be performed.")

        size_ml = Decimal(item.size_ml)
        conversion_base = Decimal('1000')

        def to_decimal(value):
            return value if isinstance(value, Decimal) else Decimal(value)

        if quantity is not None and liters is None:
            liters = (to_decimal(quantity) * size_ml) / conversion_base
            cleaned_data['liters_used'] = liters.quantize(Decimal('0.01'))
        elif liters is not None and quantity is None:
            quantity = (to_decimal(liters) * conversion_base) / size_ml
            cleaned_data['quantity_produced'] = quantity.quantize(Decimal('0.01'))
        elif quantity is not None and liters is not None:
            expected_liters = (to_decimal(quantity) * size_ml) / conversion_base
            difference = abs(expected_liters - to_decimal(liters))
            if difference > Decimal('0.05'):
                raise forms.ValidationError("Quantity Produced and Liters Used do not align with the SKU size. Please correct one of the values.")
            cleaned_data['liters_used'] = to_decimal(liters).quantize(Decimal('0.01'))
            cleaned_data['quantity_produced'] = to_decimal(quantity).quantize(Decimal('0.01'))

        return cleaned_data
