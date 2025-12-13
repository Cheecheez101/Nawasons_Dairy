from django.contrib import admin
from .models import InventoryItem, InventoryTransaction

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'product_category', 'brand', 'flavor', 'size_ml', 'current_quantity', 'needs_reorder')
    list_filter = ('unit', 'product_category', 'brand', 'is_processed')
    search_fields = ('name', 'sku', 'brand', 'flavor')

@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ('item', 'quantity', 'reason', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('item__name', 'reason')
