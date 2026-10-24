from django.urls import path

from . import views

urlpatterns = [
    path("factuur/<int:pk>/pdf/", views.pdf, name="invoice_pdf"),
    path("mijn/facturen/", views.my_invoices, name="my_invoices"),
    path("mijn/facturen/<int:pk>/sturen/", views.send_to_me, name="invoice_send_to_me"),
]
