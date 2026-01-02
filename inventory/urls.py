from django.urls import path
from .views import (
    InventoryDashboardView,
    InventoryItemCreateView,
    InventoryItemUpdateView,
    InventoryItemDeleteView,
)

app_name = 'inventory'

urlpatterns = [
    path('', InventoryDashboardView.as_view(), name='dashboard'),
    path('items/add/', InventoryItemCreateView.as_view(), name='item_create'),
    path('items/<int:pk>/edit/', InventoryItemUpdateView.as_view(), name='item_update'),
    path('items/<int:pk>/delete/', InventoryItemDeleteView.as_view(), name='item_delete'),
]
