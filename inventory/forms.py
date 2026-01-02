from django import forms

from .models import InventoryItem


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = [
            "name",
            "sku",
            "unit",
            "current_quantity",
            "reorder_threshold",
            "reorder_quantity",
            "supplier_name",
            "default_price",
            "product_category",
            "brand",
            "flavor",
            "size_ml",
            "is_processed",
            "expiry_date",
            "batch_id",
        ]
        widgets = {
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
        }
