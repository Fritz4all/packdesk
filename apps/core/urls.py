from django.urls import path

from . import setup_views, views

urlpatterns = [
    path("", views.home, name="home"),
    path("my/", views.dashboard, name="dashboard"),
    path("setup/", setup_views.wizard, name="setup"),
    path("setup/<str:step>/", setup_views.wizard, name="setup_step"),
]
