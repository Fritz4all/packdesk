from django.urls import path

from . import views

urlpatterns = [
    path("mijn/bestellen/", views.order_packs, name="order_packs"),
    path("mijn/bestellen/geplaatst/", views.done, name="order_done"),
    path("mijn/bestellingen/", views.my_orders, name="my_orders"),
    path("mijn/bestellingen/<int:pk>/", views.order_detail, name="order_detail"),
    path("mijn/licenties/", views.my_licences, name="my_licences"),
    path("mijn/licenties/<int:pk>/verlengen/", views.extend, name="extend_licence"),
]
