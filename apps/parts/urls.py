from django.urls import path

from . import views

urlpatterns = [
    path("mijn/onderdelen/", views.overview, name="my_parts"),
    path("mijn/onderdelen/aanvragen/", views.new_request, name="new_part_request"),
    path("mijn/onderdelen/aanvraag/<int:pk>/", views.request_detail, name="part_request"),
    path("mijn/onderdelen/bestelling/<int:pk>/", views.order_detail, name="part_order"),
]
