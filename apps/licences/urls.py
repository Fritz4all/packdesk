from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.licence_step, name="register_licence"),
    path("register/end-customer/", views.end_customer_step, name="register_end_customer"),
    path("register/reseller/", views.reseller_step, name="register_reseller"),
    path("register/device/", views.device_step, name="register_device"),
    path("register/monitor/", views.monitor_step, name="register_monitor"),
    path("register/options/", views.options_step, name="register_options"),
    path("register/check/", views.check_step, name="register_check"),
    path("register/done/", views.done, name="register_done"),
]
