from django.urls import path

from . import views

app_name = 'storage'

urlpatterns = [
    path('', views.storage_list, name='storage_list'),
    path('inventory/add/', views.inventory_add, name='inventory_add'),
    path('inventory/<int:pk>/edit/', views.inventory_edit, name='inventory_edit'),
    path('inventory/<int:pk>/delete/', views.inventory_delete, name='inventory_delete'),
    path('locations/', views.storage_locations, name='storage_locations'),
    path('locations/add/', views.location_add, name='location_add'),
    path('locations/<int:pk>/edit/', views.location_edit, name='location_edit'),
    path('locations/<int:pk>/delete/', views.location_delete, name='location_delete'),
    # Packaging CRUD
    path('packaging/', views.packaging_list, name='packaging_list'),
    path('packaging/add/', views.packaging_create, name='packaging_create'),
    path('packaging/<int:pk>/', views.packaging_detail, name='packaging_detail'),
    path('packaging/<int:pk>/edit/', views.packaging_edit, name='packaging_edit'),
    path('expired/', views.expired_inventory_dashboard, name='expired_inventory_dashboard'),
    path('expired/<int:pk>/remove/', views.expired_inventory_remove, name='expired_inventory_remove'),
    path('expired/<int:pk>/edit/', views.expired_inventory_edit, name='expired_inventory_edit'),
    path('inventory/<int:pk>/move_to_expired/', views.move_to_expired, name='move_to_expired'),
    path('export/pdf/', views.export_inventory_pdf, name='export_inventory_pdf'),
    path('export/excel/', views.export_inventory_excel, name='export_inventory_excel'),
]
