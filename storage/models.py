from django.db import models
from django.utils import timezone


class StorageLocation(models.Model):
    LOCATION_TYPES = [
        ("cold_room", "Cold Room"),
        ("fermentation_zone", "Fermentation Chill Zone"),
        ("ambient_store", "Ambient Store"),
        ("blast_chiller", "Blast Chiller"),
        ("dry_store", "Dry Storage"),
        ("quarantine", "Spoilt / Quarantine Zone"),
    ]

    name = models.CharField(max_length=100, unique=True)
    location_type = models.CharField(max_length=30, choices=LOCATION_TYPES, default="cold_room")
    description = models.TextField(blank=True)
    capacity = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_location_type_display()})"


class ColdStorageInventory(models.Model):
    STATUS_CHOICES = [
        ("in_storage", "✅ In cold storage"),
        ("near_expiry", "⏳ Near expiry — prioritize dispatch"),
        ("expired", "❌ Expired — block dispatch"),
    ]

    storage_id = models.AutoField(primary_key=True)
    production_batch = models.OneToOneField(
        "production.ProductionBatch",
        on_delete=models.CASCADE,
        related_name="storage_record",
    )
    product = models.CharField(max_length=100)
    expiry_date = models.DateField()
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    location = models.ForeignKey(
        StorageLocation,
        on_delete=models.PROTECT,
        related_name="inventory",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="in_storage")
    last_restocked = models.DateTimeField(auto_now_add=True)
    audit_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["expiry_date"]

    def __str__(self):
        return f"Storage #{self.storage_id} - {self.product}"

    def update_status(self):
        today = timezone.now().date()
        if self.expiry_date < today:
            self.status = "expired"
        elif (self.expiry_date - today).days <= 3:
            self.status = "near_expiry"
        else:
            self.status = "in_storage"
        self.save(update_fields=["status"])
