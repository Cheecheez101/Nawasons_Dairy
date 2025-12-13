from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('docs/chapter1/', views.docs_chapter1, name='docs_chapter1'),
]

