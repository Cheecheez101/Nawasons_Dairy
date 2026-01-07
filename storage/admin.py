from django.contrib import admin
from .models import ExpiredStockInventory

@admin.register(ExpiredStockInventory)
class ExpiredStockInventoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'packaging', 'cartons', 'loose_units', 'expiry_date', 'storage_location', 'removed_at')
    search_fields = ('product__name', 'batch_id', 'packaging__product__name')
    list_filter = ('expiry_date', 'storage_location')
from django.contrib import admin

from .models import ColdStorageInventory, StorageLocation, Packaging


@admin.register(StorageLocation)
class StorageLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "location_type", "capacity")
    list_filter = ("location_type",)
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(ColdStorageInventory)
class ColdStorageInventoryAdmin(admin.ModelAdmin):
    list_display = (
        "storage_id",
        "packaging",
        "production_batch",
        "cartons",
        "loose_units",
        "location",
        "expiry_date",
        "status",
    )
    list_filter = ("status", "location", "packaging")
    search_fields = ("packaging__product__name", "production_batch__sku", "production_batch__id")
    autocomplete_fields = ("production_batch", "location", "packaging")
    date_hierarchy = "expiry_date"
    ordering = ("expiry_date",)


@admin.register(Packaging)
class PackagingAdmin(admin.ModelAdmin):
    list_display = ("product", "pack_size_ml", "packets_per_carton", "created_at", "updated_at")
    search_fields = ("product__name",)
    list_filter = ("product", "pack_size_ml")
    ordering = ("product", "pack_size_ml")
