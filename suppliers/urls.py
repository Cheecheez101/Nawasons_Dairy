from django.urls import path

from .views import (
    SupplierManageView,
    SupplierOrderCreateView,
    SupplierOrderListView,
    SupplierOrderUpdateView,
)

app_name = 'suppliers'

urlpatterns = [
    path('', SupplierOrderListView.as_view(), name='order_list'),
    path('manage/', SupplierManageView.as_view(), name='manage'),
    path('order/<int:item_id>/', SupplierOrderCreateView.as_view(), name='create_order'),
    path('order/<int:pk>/status/', SupplierOrderUpdateView.as_view(), name='update_order'),
]
