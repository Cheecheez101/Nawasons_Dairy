from django.contrib import admin

from .models import Batch, BatchTest, LabBatchApproval


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"session",
		"collection_date",
		"state",
		"opened_at",
		"closed_at",
		"total_volume",
	)
	list_filter = ("session", "state", "collection_date")
	search_fields = ("id", "session")
	readonly_fields = ("opened_at", "reopened_at", "closed_at", "created_at")
	date_hierarchy = "collection_date"
	ordering = ("-collection_date", "-opened_at")
	list_editable = ("session", "collection_date", "state")

	def total_volume(self, obj):
		return obj.total_volume_litres()

	total_volume.short_description = "Litres"


@admin.register(BatchTest)
class BatchTestAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"batch",
		"fat_percentage",
		"snf_percentage",
		"acidity",
		"result",
		"tested_by",
		"tested_at",
	)
	list_filter = ("result", "tested_at")
	search_fields = ("batch__session", "tested_by__username")
	date_hierarchy = "tested_at"
	ordering = ("-tested_at",)


@admin.register(LabBatchApproval)
class LabBatchApprovalAdmin(admin.ModelAdmin):
	list_display = (
		"production_batch",
		"overall_result",
		"expiry_date",
		"approved_by",
		"approved_at",
	)
	list_filter = ("overall_result", "expiry_date")
	search_fields = ("production_batch__sku", "production_batch__product_type")
	date_hierarchy = "approved_at"
	ordering = ("-approved_at",)
