from django.urls import path

from . import views

urlpatterns = [
    path("registreren/", views.licence_step, name="register_licence"),
    path("registreren/eindklant/", views.end_customer_step, name="register_end_customer"),
    path("registreren/reseller/", views.reseller_step, name="register_reseller"),
    path("registreren/apparaat/", views.device_step, name="register_device"),
    path("registreren/beeldscherm/", views.monitor_step, name="register_monitor"),
    path("registreren/opties/", views.options_step, name="register_options"),
    path("registreren/controle/", views.check_step, name="register_check"),
    path("registreren/klaar/", views.done, name="register_done"),
]
