from django.urls import path

from . import views

urlpatterns = [
    path("my/items/", views.my_items, name="my_cmdb_items"),
]
