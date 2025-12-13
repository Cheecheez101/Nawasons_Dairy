from django.urls import path
from .views import SalesDashboardView, SalesCreateView, SalesReceiptView

app_name = 'sales'

urlpatterns = [
    path('', SalesDashboardView.as_view(), name='dashboard'),
    path('new/', SalesCreateView.as_view(), name='create'),
    path('receipt/<int:pk>/', SalesReceiptView.as_view(), name='receipt'),
]
