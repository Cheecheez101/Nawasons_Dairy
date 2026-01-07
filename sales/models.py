from django.db import models
from inventory.models import InventoryItem
from storage.models import Packaging
from customers.models import Customer
import uuid

def generate_transaction_id():
    return uuid.uuid4().hex[:12].upper()

# Create your models here.
class SalesTransaction(models.Model):
    PAYMENT_STATUSES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('refunded', 'Refunded'),
    ]

    PAYMENT_MODES = [
        ('cash', 'Cash'),
        ('mpesa', 'M-Pesa'),
        ('card', 'Card'),
    ]

    transaction_id = models.CharField(max_length=12, unique=True, default=generate_transaction_id, editable=False)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name='sales')
    walk_in_customer_name = models.CharField(max_length=120, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUSES, default='pending')
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODES, default='cash')
    payment_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.transaction_id

    @property
    def customer_display_name(self):
        if self.customer:
            return self.customer.name
        if self.walk_in_customer_name:
            return self.walk_in_customer_name
        if self.customer_phone:
            return f"Walk-in ({self.customer_phone})"
        return 'Walk-in customer'

class SalesItem(models.Model):
    transaction = models.ForeignKey(SalesTransaction, related_name='items', on_delete=models.CASCADE)
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)
    # Optional packet/carton based sale fields
    cartons = models.PositiveIntegerField(default=0)
    loose_units = models.PositiveIntegerField(default=0)
    # Optional bulk price applied per carton when provided
    bulk_price_per_carton = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    SOLD_AS_CHOICES = [
        ('unit', 'Unit'),
        ('carton', 'Carton'),
    ]
    # Records whether the item was sold as loose unit or as cartons
    sold_as = models.CharField(max_length=10, choices=SOLD_AS_CHOICES, default='unit')

    # Where the bulk price was sourced from: packaging, product-level price, or manual override
    BULK_PRICE_SOURCE_CHOICES = [
        ('packaging', 'Packaging'),
        ('product', 'ProductPrice'),
        ('manual', 'Manual'),
    ]
    bulk_price_source = models.CharField(max_length=20, choices=BULK_PRICE_SOURCE_CHOICES, null=True, blank=True)

    def __str__(self):
        if self.cartons or self.loose_units:
            return f"{self.inventory_item.name} - {self.cartons} cartons + {self.loose_units} loose"
        return f"{self.inventory_item.name} x {self.quantity}"

    @property
    def line_total(self):
        # If cartons/loose_units provided, compute using packaging when possible
        try:
            if self.cartons or self.loose_units:
                pkg = Packaging.objects.filter(product=self.inventory_item).order_by('-pack_size_ml').first()
                per_carton = pkg.packets_per_carton if pkg else 1
                loose = int(self.loose_units or 0)
                cartons = int(self.cartons or 0)
                if self.bulk_price_per_carton is not None and cartons > 0:
                    return (cartons * self.bulk_price_per_carton) + (loose * self.price_per_unit)
                return ((cartons * per_carton) + loose) * self.price_per_unit
        except Exception:
            pass
        return self.quantity * self.price_per_unit
