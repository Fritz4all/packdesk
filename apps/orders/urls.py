from django.urls import path

from . import views

urlpatterns = [
    path("my/order/", views.order_packs, name="order_packs"),
    path("my/order/placed/", views.done, name="order_done"),
    path("my/orders/", views.my_orders, name="my_orders"),
    path("my/orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("my/licences/", views.my_licences, name="my_licences"),
    path("my/licences/<int:pk>/extend/", views.extend, name="extend_licence"),
]
