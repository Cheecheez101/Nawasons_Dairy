from django.urls import path
from .views import CustomerDashboardView, CustomerCreateView, CustomerUpdateView, LoyaltyAdjustView, LoyaltyExportView, CustomerDeleteView

app_name = 'customers'

urlpatterns = [
    path('', CustomerDashboardView.as_view(), name='index'),
    path('new/', CustomerCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', CustomerUpdateView.as_view(), name='edit'),
    path('<int:pk>/loyalty/', LoyaltyAdjustView.as_view(), name='loyalty'),
    path('<int:pk>/loyalty/export/', LoyaltyExportView.as_view(), name='loyalty_export'),
    path('<int:pk>/delete/', CustomerDeleteView.as_view(), name='delete'),
]
