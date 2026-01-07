"""
URL configuration for nawasons_dairy project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.shortcuts import render

# Custom error handlers
def custom_permission_denied_view(request, exception=None):
    return render(request, '403.html', status=403)

handler403 = custom_permission_denied_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include(('core.urls', 'core'), namespace='core')),
    path('production/', include('production.urls')),
    path('inventory/', include('inventory.urls')),
    path('sales/', include('sales.urls')),
    path('sellers/', include('sellers.urls')),
    path('customers/', include('customers.urls')),
    path('suppliers/', include('suppliers.urls')),
    path('reports/', include('reports.urls')),
    path('lab/', include('lab.urls')),
    path('storage/', include('storage.urls')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)