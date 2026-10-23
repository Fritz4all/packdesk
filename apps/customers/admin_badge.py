from .models import Customer


def pending(request):
    """Number of sign-ups waiting for approval (shown in the admin menu)."""
    if not request.user.has_perm("customers.view_customer"):
        return ""
    count = Customer.objects.filter(status=Customer.Status.PENDING).count()
    return str(count) if count else ""
