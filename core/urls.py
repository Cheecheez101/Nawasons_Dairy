from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('access/next/', views.next_access, name='next_access'),
    path('docs/chapter1/', views.docs_chapter1, name='docs_chapter1'),
    path('users/manage/', views.user_management, name='user_management'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('settings/profile/', views.profile_settings, name='profile_settings'),
]

