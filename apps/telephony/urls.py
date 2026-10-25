from django.urls import path

from . import views

urlpatterns = [
    path("mijn/telefonie/", views.calculator, name="telephony_calculator"),
    path("mijn/telefonie/offertes/", views.my_quotes, name="telephony_quotes"),
    path("mijn/telefonie/offertes/<int:pk>/", views.quote_detail, name="telephony_quote"),
]
