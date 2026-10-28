from django.urls import path

from . import views

urlpatterns = [
    path("hardware/", views.shop, name="hardware_shop"),
    path("hardware/<str:number>/", views.device_detail, name="hardware_device"),
]
