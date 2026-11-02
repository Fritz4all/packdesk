from django.utils.functional import SimpleLazyObject


def cmdb(request):
    """Whether this login sees the CMDB card; only worked out on a page that asks."""
    from .views import portal_customer

    user = getattr(request, "user", None)
    return {"cmdb_portal": SimpleLazyObject(lambda: portal_customer(user) is not None if user is not None else False)}
