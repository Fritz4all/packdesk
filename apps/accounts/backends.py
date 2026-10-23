from django.contrib.auth.backends import ModelBackend

from .models import User


class EmailBackend(ModelBackend):
    """Authenticates with email address + password (case-insensitive email)."""

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        email = (email or username or "").strip().lower()
        if not email or password is None:
            return None
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            User().set_password(password)  # same work as a real check, against timing attacks
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
