from django.urls import path

from . import views

urlpatterns = [
    path("invoice/<int:pk>/pdf/", views.pdf, name="invoice_pdf"),
    path("my/invoices/", views.my_invoices, name="my_invoices"),
    path("my/invoices/<int:pk>/send/", views.send_to_me, name="invoice_send_to_me"),
]
