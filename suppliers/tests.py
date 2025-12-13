from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from inventory.models import InventoryItem
from .models import Supplier, SupplierOrder

class SupplierOrderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='testuser', password='pass')
        self.user.user_permissions.set([])
        self.inventory_item = InventoryItem.objects.create(name='Milk', sku='MILK1', current_quantity=10, reorder_threshold=5, reorder_quantity=20)
        self.supplier = Supplier.objects.create(name='Supplier A', contact_person='John', phone='123')

    def test_mark_order_delivered_updates_inventory(self):
        order = SupplierOrder.objects.create(supplier=self.supplier, inventory_item=self.inventory_item, quantity=15, expected_delivery='2024-01-01')
        self.client.force_login(self.user)
        response = self.client.post(reverse('suppliers:update_order', args=[order.pk]), {'status': 'delivered'})
        self.assertEqual(response.status_code, 302)
        self.inventory_item.refresh_from_db()
        self.assertEqual(self.inventory_item.current_quantity, 25)
