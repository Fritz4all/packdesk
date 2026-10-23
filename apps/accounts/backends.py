from django.contrib.auth.backends import ModelBackend

from .models import User


class TenantEmailBackend(ModelBackend):
    """Authenticates with email + password within the tenant of the request.

    On a platform host only platform staff (users without tenant) can log in.
    """

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        email = (email or username or "").strip().lower()
        if not email or password is None or request is None:
            return None
        tenant = getattr(request, "tenant", None)
        try:
            user = User.objects.get(email=email, tenant=tenant)
        except User.DoesNotExist:
            User().set_password(password)  # same work as a real check, against timing attacks
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
