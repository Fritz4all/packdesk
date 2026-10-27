from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("signup/sent/", views.signup_done, name="signup_done"),
    path("my/details/", views.my_details, name="my_details"),
]
