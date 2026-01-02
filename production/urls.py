from django.urls import path
from .views import (
    CowListView,
    CowCreateView,
    MilkYieldCreateView,
    MilkYieldDeleteView,
    MilkYieldExportView,
    MilkYieldUpdateView,
    ProductPriceCreateView,
    ProductPriceListView,
    ProductPriceUpdateView,
    batch_form,
)

app_name = 'production'

urlpatterns = [
    path('', CowListView.as_view(), name='cow_list'),
    path("batch/form/", batch_form, name="batch_form"),
    path('cows/new/', CowCreateView.as_view(), name='cow_create'),
    path('yields/new/', MilkYieldCreateView.as_view(), name='yield_create'),
    path('yields/<int:pk>/edit/', MilkYieldUpdateView.as_view(), name='yield_edit'),
    path('yields/<int:pk>/delete/', MilkYieldDeleteView.as_view(), name='yield_delete'),
    path('yields/export/', MilkYieldExportView.as_view(), name='yield_export'),
    path('prices/', ProductPriceListView.as_view(), name='price_list'),
    path('prices/new/', ProductPriceCreateView.as_view(), name='price_create'),
    path('prices/<int:pk>/edit/', ProductPriceUpdateView.as_view(), name='price_update'),
]
