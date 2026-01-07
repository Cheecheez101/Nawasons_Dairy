from django.urls import path
from . import views

urlpatterns = [
    path('add/', views.add_seller, name='add_seller'),
    path('serve/', views.serve_seller, name='serve_seller'),
    path('list/', views.seller_list, name='seller_list'),
    path('transactions/', views.seller_transactions, name='seller_transactions'),
    path('report/distribution/', views.seller_distribution_report, name='seller_distribution_report'),
    path('report/product/', views.seller_product_report, name='seller_product_report'),
    path('report/combined/', views.combined_inventory_impact_report, name='combined_inventory_impact_report'),
]
