from django.urls import path
from .views import (
    SalesDashboardView,
    SalesCreateView,
    SalesReceiptView,
    SalesUpdateView,
    SalesDeleteView,
)

app_name = 'sales'

urlpatterns = [
    path('', SalesDashboardView.as_view(), name='dashboard'),
    path('new/', SalesCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', SalesUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', SalesDeleteView.as_view(), name='delete'),
    path('receipt/<int:pk>/', SalesReceiptView.as_view(), name='receipt'),
]
