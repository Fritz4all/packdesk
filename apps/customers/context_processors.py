from .models import SignupSettings, customer_of


def customer(request):
    user = getattr(request, "user", None)
    return {
        "signup_settings": SignupSettings.load(),
        "current_customer": customer_of(user) if user is not None else None,
    }
