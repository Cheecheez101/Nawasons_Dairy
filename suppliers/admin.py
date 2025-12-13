from django.contrib import admin
from .models import Supplier, SupplierOrder

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'phone', 'lead_time_days')
    search_fields = ('name', 'contact_person')

@admin.register(SupplierOrder)
class SupplierOrderAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'inventory_item', 'quantity', 'status', 'expected_delivery')
    list_filter = ('status',)
