from django.urls import path

from . import views

urlpatterns = [
    path("report-fault/", views.report, name="fault_report"),
    path("report-fault/sent/", views.done, name="fault_done"),
    path("my/faults/", views.my_reports, name="my_fault_reports"),
    path("fault-attachment/<int:pk>/", views.attachment, name="fault_attachment"),
]
