from django.urls import path

from . import order_views, views

urlpatterns = [
    path("hardware/", views.shop, name="hardware_shop"),
    path("hardware/cart/", order_views.cart, name="hardware_cart"),
    path("hardware/ordered/", order_views.done, name="hardware_done"),
    path("hardware/<str:number>/", views.device_detail, name="hardware_device"),
    path("hardware/<str:number>/add/", order_views.add, name="hardware_add"),
    path("hardware/<str:number>/remove/", order_views.remove, name="hardware_remove"),
]
