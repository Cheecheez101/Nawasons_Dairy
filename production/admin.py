from django.contrib import admin
from .models import Cow, MilkYield, ProductPrice, ProductPriceChangeLog, ProductionBatch

@admin.register(Cow)
class CowAdmin(admin.ModelAdmin):
    list_display = ('cow_id', 'breed', 'health_status', 'daily_capacity_litres')
    search_fields = ('cow_id', 'breed')

@admin.register(MilkYield)
class MilkYieldAdmin(admin.ModelAdmin):
    list_display = ('cow', 'recorded_at', 'session', 'yield_litres', 'storage_tank', 'quality_grade')
    list_filter = ('recorded_at', 'session', 'quality_grade')

@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    list_display = ('product_name', 'sku', 'price', 'last_updated', 'updated_by')
    list_filter = ('last_updated',)
    search_fields = ('product_name', 'sku')
    readonly_fields = ('sku', 'product_name', 'last_updated', 'updated_by')


@admin.register(ProductPriceChangeLog)
class ProductPriceChangeLogAdmin(admin.ModelAdmin):
    list_display = ('product_price', 'old_price', 'new_price', 'changed_by', 'changed_at')
    list_filter = ('changed_at',)
    search_fields = ('product_price__product_name', 'product_price__sku', 'changed_by__username')
    readonly_fields = ('product_price', 'old_price', 'new_price', 'changed_by', 'changed_at')


@admin.register(ProductionBatch)
class ProductionBatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'product_type', 'sku', 'source_tank', 'status', 'produced_at')
    list_filter = ('status', 'product_type', 'source_tank')
    search_fields = ('sku', 'product_type', 'source_tank')
    ordering = ('-produced_at',)
