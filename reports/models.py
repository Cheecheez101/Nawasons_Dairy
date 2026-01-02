from django.contrib.auth import get_user_model
from django.db import models


class Report(models.Model):
	"""Stores generated analytics or uploaded report files for auditing."""

	REPORT_TYPES = [
		("inventory", "Inventory"),
		("sales", "Sales"),
		("production", "Production"),
		("lab", "Lab"),
		("custom", "Custom"),
	]

	title = models.CharField(max_length=150)
	report_type = models.CharField(max_length=20, choices=REPORT_TYPES, default="custom")
	description = models.TextField(blank=True)
	generated_on = models.DateTimeField(auto_now_add=True)
	generated_by = models.ForeignKey(
		get_user_model(),
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="generated_reports",
	)
	file = models.FileField(upload_to="reports/files/", blank=True, null=True)
	is_public = models.BooleanField(default=False)

	class Meta:
		ordering = ["-generated_on"]
		permissions = [
			("view_reports_dashboard", "Can view reports dashboard"),
			("export_reports", "Can export and download reports"),
		]

	def __str__(self) -> str:
		return self.title
