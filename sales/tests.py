from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from inventory.models import InventoryItem
from .models import SalesTransaction, SalesItem

class SalesFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='sales', password='pass')
        perms = Permission.objects.filter(codename__in=['add_salestransaction'])
        self.user.user_permissions.set(perms)
        self.item = InventoryItem.objects.create(name='Milk', sku='MILK1', current_quantity=50, reorder_threshold=5, reorder_quantity=20)

    def test_sale_deducts_inventory(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sales:create'), {
            'transaction_id': 'TX123',
            'customer_name': 'John',
            'customer_phone': '123',
            'total_amount': '0',
            'payment_status': 'paid',
            'payment_reference': 'REF',
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-inventory_item': self.item.pk,
            'form-0-quantity': '10',
            'form-0-price_per_unit': '5',
        })
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_quantity, 40)
