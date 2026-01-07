from django.contrib import admin
from .models import Seller, SellerTransaction

@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone_number', 'location', 'seller_type', 'created_at')
    search_fields = ('name', 'phone_number', 'location')
    list_filter = ('seller_type', 'created_at')

@admin.register(SellerTransaction)
class SellerTransactionAdmin(admin.ModelAdmin):
    list_display = ('seller', 'product', 'packaging', 'quantity', 'transaction_date', 'status')
    search_fields = ('seller__name', 'product__name')
    list_filter = ('status', 'transaction_date', 'seller')
