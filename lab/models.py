from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from production.models import MilkYield, ProductionBatch
from datetime import timedelta

class RawMilkTest(models.Model):
    RESULT_CHOICES = [
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("pending", "Pending"),
    ]

    milk_yield = models.OneToOneField(MilkYield, on_delete=models.CASCADE, related_name="raw_test")
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default="pending")
    tested_at = models.DateTimeField(auto_now_add=True)
    tested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-tested_at"]

    def __str__(self):
        return f"Raw test for yield {self.milk_yield_id} - {self.result}"

    def clean(self):
        """
        Prevent approving a milk yield that's already approved by lab.
        """
        # If attempting to set this test to approved, but the MilkYield already
        # has raw_test_approved=True and this change would represent a new
        # approval (i.e. this record was not already approved), raise.
        if self.result == "approved":
            # Determine previous state of this RawMilkTest (if it exists)
            previous_result = None
            if self.pk:
                try:
                    prev = RawMilkTest.objects.get(pk=self.pk)
                    previous_result = prev.result
                except RawMilkTest.DoesNotExist:
                    previous_result = None

            if self.milk_yield.raw_test_approved and previous_result != "approved":
                raise ValidationError("This milk yield has already been approved and cannot be approved again.")

    def save(self, *args, **kwargs):
        """
        After saving the test, update the related MilkYield flags:
        - If approved: mark milk_yield.raw_test_approved = True
        - If rejected: move milk_yield to 'Spoilt Tank' and ensure raw_test_approved = False
        """
        # Validate before saving
        self.full_clean()

        creating = self.pk is None
        previous_result = None
        if not creating:
            try:
                previous_result = RawMilkTest.objects.get(pk=self.pk).result
            except RawMilkTest.DoesNotExist:
                previous_result = None

        super().save(*args, **kwargs)

        # Update MilkYield based on the result
        if self.result == "approved":
            if not self.milk_yield.raw_test_approved:
                self.milk_yield.raw_test_approved = True
                self.milk_yield.save(update_fields=["raw_test_approved"])
        elif self.result == "rejected":
            # Move to spoilt tank and clear approval flag
            self.milk_yield.storage_tank = "Spoilt Tank"
            if self.milk_yield.raw_test_approved:
                self.milk_yield.raw_test_approved = False
            self.milk_yield.save(update_fields=["storage_tank", "raw_test_approved"])


class TankBatchTest(models.Model):
    RESULT_CHOICES = [
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("pending", "Pending"),
    ]

    milk_yield = models.ForeignKey(MilkYield, on_delete=models.CASCADE, related_name="tank_tests")
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default="pending")
    notes = models.TextField(blank=True)
    tested_at = models.DateTimeField(auto_now_add=True)
    tested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-tested_at"]

    def __str__(self):
        return f"Tank test for yield {self.milk_yield_id} - {self.result}"


class LabBatchApproval(models.Model):
    RESULT_CHOICES = [
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("pending", "Pending"),
    ]

    production_batch = models.OneToOneField(
        ProductionBatch,
        on_delete=models.CASCADE,
        related_name="lab_approval",
        null=True,  # allow existing rows to stay valid
        blank=True  # allow admin/forms to leave it empty temporarily
    )

    overall_result = models.CharField(max_length=20, choices=RESULT_CHOICES, default="pending")
    expiry_date = models.DateField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lab_batch_approvals")
    approved_at = models.DateTimeField(auto_now_add=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-approved_at"]
        permissions = [
            ("approve_milk_batch", "Can approve or reject milk batches"),
            ("issue_expiry", "Can issue expiry dates for approved batches"),
        ]

    def __str__(self):
        return f"Batch {self.production_batch_id} - {self.overall_result}"

    def set_expiry(self, shelf_life_days=7):
        self.expiry_date = timezone.now().date() + timedelta(days=shelf_life_days)
        self.save()
