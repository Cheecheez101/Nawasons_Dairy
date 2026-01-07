from django.db import models
from inventory.models import InventoryItem
from storage.models import Packaging

class Seller(models.Model):
    DISTRIBUTOR = 'distributor'
    RETAILER = 'retailer'
    AGENT = 'agent'
    SELLER_TYPE_CHOICES = [
        (DISTRIBUTOR, 'Distributor'),
        (RETAILER, 'Retailer'),
        (AGENT, 'Agent'),
    ]
    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    location = models.CharField(max_length=100)
    seller_type = models.CharField(max_length=20, choices=SELLER_TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_seller_type_display()})"

class SellerTransaction(models.Model):
    SERVED = 'served'
    PENDING = 'pending'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (SERVED, 'Served'),
        (PENDING, 'Pending'),
        (CANCELLED, 'Cancelled'),
    ]
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE)
    product = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    packaging = models.ForeignKey(Packaging, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    transaction_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    def __str__(self):
        return f"{self.seller.name} - {self.product.name} ({self.quantity})"
