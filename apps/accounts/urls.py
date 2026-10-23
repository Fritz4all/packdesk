from django.contrib.auth import views as auth_views
from django.urls import path

from .forms import EmailAuthenticationForm

urlpatterns = [
    path(
        "inloggen/",
        auth_views.LoginView.as_view(authentication_form=EmailAuthenticationForm, redirect_authenticated_user=True),
        name="login",
    ),
    path("uitloggen/", auth_views.LogoutView.as_view(), name="logout"),
]
