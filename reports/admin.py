from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
	list_display = ("title", "report_type", "generated_on", "generated_by", "is_public")
	list_filter = ("report_type", "is_public")
	search_fields = ("title", "description")
