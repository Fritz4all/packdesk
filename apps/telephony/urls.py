from django.urls import path

from . import views

urlpatterns = [
    path("my/telephony/", views.calculator, name="telephony_calculator"),
    path("my/telephony/quotes/", views.my_quotes, name="telephony_quotes"),
    path("my/telephony/quotes/<int:pk>/", views.quote_detail, name="telephony_quote"),
]
