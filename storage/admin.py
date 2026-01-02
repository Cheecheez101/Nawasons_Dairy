from django.contrib import admin

from .models import ColdStorageInventory, StorageLocation


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
        "product",
        "production_batch",
        "location",
        "expiry_date",
        "status",
    )
    list_filter = ("status", "location")
    search_fields = ("product", "production_batch__sku", "production_batch__id")
    autocomplete_fields = ("production_batch", "location")
    date_hierarchy = "expiry_date"
    ordering = ("expiry_date",)
