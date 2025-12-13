from django.db import models
from inventory.models import InventoryItem
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

class SalesItem(models.Model):
    transaction = models.ForeignKey(SalesTransaction, related_name='items', on_delete=models.CASCADE)
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.inventory_item.name} x {self.quantity}"

    @property
    def line_total(self):
        return self.quantity * self.price_per_unit
