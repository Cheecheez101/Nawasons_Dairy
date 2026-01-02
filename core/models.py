from django.contrib.auth import get_user_model
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(get_user_model(), on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to="profiles/", blank=True, null=True)
    phone_number = models.CharField(max_length=30, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    location = models.CharField(max_length=120, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]
        permissions = [
            ("view_dashboard", "Can access main dashboard"),
        ]

    def __str__(self):
        return f"Profile for {self.user.get_username()}"


class DataQualityAlert(models.Model):
    SEVERITY_CHOICES = [
        ("warning", "Warning"),
        ("critical", "Critical"),
    ]

    code = models.CharField(max_length=120, unique=True)
    category = models.CharField(max_length=60)
    message = models.TextField()
    model_label = models.CharField(max_length=120, blank=True)
    record_id = models.CharField(max_length=64, blank=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="warning")
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    auto_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-detected_at"]

    def __str__(self):
        return f"{self.category}: {self.message[:50]}"
