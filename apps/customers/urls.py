from django.urls import path

from . import views

urlpatterns = [
    path("aanmelden/", views.signup, name="signup"),
    path("aanmelden/verzonden/", views.signup_done, name="signup_done"),
    path("mijn/gegevens/", views.my_details, name="my_details"),
]
