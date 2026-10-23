from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .forms import EmailAuthenticationForm
from .views import PasswordResetView

urlpatterns = [
    path(
        "inloggen/",
        auth_views.LoginView.as_view(authentication_form=EmailAuthenticationForm, redirect_authenticated_user=True),
        name="login",
    ),
    path("uitloggen/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "wachtwoord-vergeten/",
        PasswordResetView.as_view(),
        name="password_reset",
    ),
    path("wachtwoord-vergeten/verzonden/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "wachtwoord-instellen/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("wachtwoord-instellen/klaar/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path(
        "mijn/wachtwoord/",
        auth_views.PasswordChangeView.as_view(success_url=reverse_lazy("password_change_done")),
        name="password_change",
    ),
    path("mijn/wachtwoord/gewijzigd/", auth_views.PasswordChangeDoneView.as_view(), name="password_change_done"),
]
