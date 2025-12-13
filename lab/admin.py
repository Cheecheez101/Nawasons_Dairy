from django.contrib import admin
from .models import RawMilkTest, TankBatchTest, LabBatchApproval


@admin.register(RawMilkTest)
class RawMilkTestAdmin(admin.ModelAdmin):
    list_display = ("milk_yield", "result", "tested_by", "tested_at")
    list_filter = ("result",)
    search_fields = ("milk_yield__cow__cow_id",)


@admin.register(TankBatchTest)
class TankBatchTestAdmin(admin.ModelAdmin):
    list_display = ("milk_yield", "result", "tested_by", "tested_at", "notes")
    list_filter = ("result",)
    search_fields = ("milk_yield__cow__cow_id", "notes")


@admin.register(LabBatchApproval)
class LabBatchApprovalAdmin(admin.ModelAdmin):
    list_display = ("production_batch", "overall_result", "approved_by", "approved_at", "expiry_date")
    list_filter = ("overall_result",)
    search_fields = ("production_batch__milk_source__cow__cow_id", "remarks")
