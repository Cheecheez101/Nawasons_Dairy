from django.db import models

class ExpiredStockInventory(models.Model):
    product = models.ForeignKey('inventory.InventoryItem', on_delete=models.CASCADE)
    packaging = models.ForeignKey('Packaging', on_delete=models.CASCADE)
    cartons = models.IntegerField(default=0)
    loose_units = models.IntegerField(default=0)
    expiry_date = models.DateField()
    batch_id = models.CharField(max_length=50, blank=True)
    storage_location = models.ForeignKey('StorageLocation', on_delete=models.CASCADE)
    removed_at = models.DateTimeField(auto_now_add=True)
    audit_notes = models.TextField(blank=True)

    def total_units(self):
        return (self.cartons * self.packaging.packets_per_carton) + self.loose_units

def move_to_expired(inventory_record, user):
    from datetime import date
    ExpiredStockInventory.objects.create(
        product=inventory_record.packaging.product,
        packaging=inventory_record.packaging,
        cartons=inventory_record.cartons,
        loose_units=inventory_record.loose_units,
        expiry_date=inventory_record.expiry_date,
        batch_id=getattr(inventory_record, 'batch_id', ''),
        storage_location=inventory_record.location,
        audit_notes=f"Expired stock moved by {user} on {date.today()}"
    )
    inventory_record.cartons = 0
    inventory_record.loose_units = 0
    inventory_record.status = 'expired'
    inventory_record.save()
from django.db import models
from django.utils import timezone


class StorageLocation(models.Model):
    LOCATION_TYPES = [
        ("cold_room", "Cold Room"),
        ("fermentation_zone", "Fermentation Chill Zone"),
        ("atms_Storage", "ATMs Storage"),
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



# --- Packaging Model ---
class Packaging(models.Model):
    product = models.ForeignKey(
        'inventory.InventoryItem',
        on_delete=models.PROTECT,
        related_name='packagings',
        help_text="The product this packaging is for."
    )
    pack_size_ml = models.PositiveIntegerField(help_text="Size of each packet in ml (e.g. 250, 500)")
    packets_per_carton = models.PositiveIntegerField(help_text="Number of packets per carton (e.g. 24, 12)")
    # Optional bulk price applied when a customer buys full cartons
    bulk_price_per_carton = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Optional: bulk price applied per carton for wholesale purchases.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("product", "pack_size_ml", "packets_per_carton")
        ordering = ["product", "pack_size_ml"]

    def __str__(self):
        return f"{self.product.name} - {self.pack_size_ml}ml x {self.packets_per_carton}/carton"


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
    packaging = models.ForeignKey(
        Packaging,
        on_delete=models.PROTECT,
        related_name="inventory_records",
        help_text="Packaging type for this inventory record.",
        null=True,
        blank=True,
    )
    expiry_date = models.DateField()
    cartons = models.PositiveIntegerField(default=0, help_text="Number of full cartons in storage.")
    loose_units = models.PositiveIntegerField(default=0, help_text="Loose packets not in cartons.")
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
        return f"Storage #{self.storage_id} - {self.packaging}"

    def update_status(self):
        today = timezone.now().date()
        if self.expiry_date < today:
            self.status = "expired"
        elif (self.expiry_date - today).days <= 3:
            self.status = "near_expiry"
        else:
            self.status = "in_storage"
        self.save(update_fields=["status"])

    def total_units(self):
        """
        Returns the total number of units (packets) in this inventory record,
        combining cartons and loose units.
        """
        try:
            if self.packaging and getattr(self.packaging, 'packets_per_carton', None):
                return (self.cartons * self.packaging.packets_per_carton) + self.loose_units
            # Packaging missing or incomplete: fall back to loose_units only
            return self.loose_units or 0
        except Exception:
            return self.loose_units or 0
