from django.urls import path

from . import views

urlpatterns = [
    path("my/items/", views.my_items, name="my_cmdb_items"),
    path("cmdb/discovery/report/", views.discovery_report, name="cmdb_discovery_report"),
]
