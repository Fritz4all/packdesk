from django.urls import path

from . import setup_views, views

urlpatterns = [
    path("", views.home, name="home"),
    path("mijn/", views.dashboard, name="dashboard"),
    path("installatie/", setup_views.wizard, name="setup"),
    path("installatie/<str:step>/", setup_views.wizard, name="setup_step"),
]
