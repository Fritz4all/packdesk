from django.urls import path

from . import views

urlpatterns = [
    path("storing-melden/", views.report, name="fault_report"),
    path("storing-melden/verzonden/", views.done, name="fault_done"),
    path("mijn/storingen/", views.my_reports, name="my_fault_reports"),
    path("storing-bijlage/<int:pk>/", views.attachment, name="fault_attachment"),
]
