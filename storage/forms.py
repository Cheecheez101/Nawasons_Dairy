from django import forms

from .models import ColdStorageInventory, StorageLocation


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

    class Meta:
        model = ColdStorageInventory
        fields = [
            'production_batch',
            'product',
            'expiry_date',
            'quantity',
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
