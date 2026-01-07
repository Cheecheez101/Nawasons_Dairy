from django import forms
from .models import ExpiredStockInventory

class ExpiredStockInventoryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_classes = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{css_classes} form-control".strip()

    class Meta:
        model = ExpiredStockInventory
        fields = [
            'product',
            'packaging',
            'cartons',
            'loose_units',
            'expiry_date',
            'batch_id',
            'storage_location',
            'audit_notes',
        ]
from django import forms

from .models import ColdStorageInventory, StorageLocation
from .models import Packaging
from inventory.models import InventoryItem
from decimal import Decimal


class PackagingForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_classes = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{css_classes} form-control".strip()

    class Meta:
        model = Packaging
        fields = [
            'product',
            'pack_size_ml',
            'packets_per_carton',
            'bulk_price_per_carton',
        ]


class StorageLocationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_classes = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{css_classes} form-control".strip()

    class Meta:
        model = StorageLocation
        fields = [
            'name',
            'location_type',
            'capacity',
            'description',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'capacity': 'Total capacity expressed in the same units used for batch quantities.',
        }


class ColdStorageInventoryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_classes = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{css_classes} form-control".strip()
        # Add a non-model helper field for total units (packets) so users can
        # enter a single quantity and have cartons/loose units calculated.
        self.fields['total_units'] = forms.IntegerField(
            required=False,
            min_value=0,
            help_text="Total packets. If provided, cartons and loose units will be computed automatically.",
            widget=forms.NumberInput(attrs={'class': 'form-control'})
        )

        # If editing an existing record, pre-fill the total_units helper
        if getattr(self, 'instance', None) and getattr(self.instance, 'pk', None):
            try:
                existing_total = self.instance.total_units()
                # If the stored cartons/loose_units give a total, use it.
                if existing_total:
                    self.initial['total_units'] = existing_total
                else:
                    # Fallback: if this lot is linked to a production batch,
                    # try to infer total units from the batch quantity and
                    # available packaging rules.
                    pb = getattr(self.instance, 'production_batch', None)
                    inferred_units = None
                    try:
                        if pb and getattr(pb, 'quantity_produced', None) is not None:
                            qty = pb.quantity_produced
                            # Prefer an explicit packaging on the lot
                            pkg = getattr(self.instance, 'packaging', None)
                            inv = None
                            if not pkg and getattr(pb, 'sku', None):
                                inv = InventoryItem.objects.filter(sku=pb.sku).first()
                                if inv:
                                    pkg = Packaging.objects.filter(product=inv).order_by('-pack_size_ml').first()

                            if pkg:
                                # If batch unit is litres, convert litres -> packets
                                if inv and getattr(inv, 'unit', None) == 'L':
                                    inferred_units = int((Decimal(str(qty)) * Decimal('1000')) // Decimal(pkg.pack_size_ml))
                                else:
                                    # If quantity has fractional part, assume litres
                                    try:
                                        if float(qty) != int(float(qty)):
                                            inferred_units = int((Decimal(str(qty)) * Decimal('1000')) // Decimal(pkg.pack_size_ml))
                                        else:
                                            inferred_units = int(Decimal(str(qty)))
                                    except Exception:
                                        inferred_units = int(Decimal(str(qty)))
                            else:
                                # No packaging available; assume the batch quantity
                                # is already a packet count.
                                inferred_units = int(Decimal(str(qty)))
                    except Exception:
                        inferred_units = None

                    if inferred_units:
                        self.initial['total_units'] = inferred_units
            except Exception:
                # If packaging is missing or calculation fails, skip prefilling
                pass

        # Reorder visible fields to place total_units before cartons/loose_units
        desired_order = [
            'production_batch', 'packaging', 'expiry_date', 'total_units',
            'cartons', 'loose_units', 'location', 'status', 'audit_notes'
        ]
        # Preserve any fields not in desired_order at the end
        for name in list(self.fields.keys()):
            if name not in desired_order:
                desired_order.append(name)
        self.fields = {k: self.fields[k] for k in desired_order if k in self.fields}

    class Meta:
        model = ColdStorageInventory
        fields = [
            'production_batch',
            'packaging',
            'expiry_date',
            # 'total_units' is intentionally not listed here because it's a
            # non-model field; it's added dynamically in __init__.
            'cartons',
            'loose_units',
            'location',
            'status',
            'audit_notes',
        ]
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'audit_notes': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'status': 'Used to drive alerts in inventory dashboard and reports.',
        }

    def clean(self):
        cleaned = super().clean()
        total_units = cleaned.get('total_units')
        packaging = cleaned.get('packaging') or (self.instance and getattr(self.instance, 'packaging', None))

        if total_units is not None:
            if not packaging:
                raise forms.ValidationError('Select a packaging rule before entering total units so cartons can be calculated.')
            per_carton = packaging.packets_per_carton
            cartons = total_units // per_carton
            loose = total_units % per_carton
            cleaned['cartons'] = cartons
            cleaned['loose_units'] = loose

        # Ensure cartons/loose_units are non-negative integers
        cartons = cleaned.get('cartons')
        loose_units = cleaned.get('loose_units')
        if cartons is None:
            cleaned['cartons'] = 0
        if loose_units is None:
            cleaned['loose_units'] = 0

        return cleaned
