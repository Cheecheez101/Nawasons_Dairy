from django.contrib import admin
from .models import Customer, CustomerInteraction, LoyaltyTier, LoyaltyLedger

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'loyalty_points', 'created_at')
    search_fields = ('name', 'phone')

@admin.register(CustomerInteraction)
class CustomerInteractionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'interaction_type', 'created_at')
    list_filter = ('interaction_type',)

@admin.register(LoyaltyTier)
class LoyaltyTierAdmin(admin.ModelAdmin):
    list_display = ('name', 'min_spend', 'max_spend', 'points_awarded')
    list_editable = ('min_spend', 'max_spend', 'points_awarded')
    ordering = ('min_spend',)

@admin.register(LoyaltyLedger)
class LoyaltyLedgerAdmin(admin.ModelAdmin):
    list_display = ('customer', 'points_change', 'balance_after', 'reason', 'created_at')
    readonly_fields = ('customer', 'points_change', 'balance_after', 'reason', 'created_at')
    ordering = ('-created_at',)
