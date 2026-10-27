"""The website used to have Dutch addresses (/inloggen/, /mijn/bestellingen/, /beheer/ ...). They are English
now; old links, bookmarks and links in sent emails lead to the new address."""

import re

from django.http import HttpResponsePermanentRedirect

# Dutch address part → English address part
WORDS = {
    "beheer": "admin", "aanmelden": "signup", "verzonden": "sent", "factuur": "invoice", "installatie": "setup",
    "database-bijwerken": "database-update", "mijn": "my", "bestellen": "order", "geplaatst": "placed",
    "bestellingen": "orders", "facturen": "invoices", "sturen": "send", "gegevens": "details",
    "licenties": "licences", "verlengen": "extend", "onderdelen": "parts", "aanvragen": "request",
    "aanvraag": "requests", "bestelling": "orders", "storingen": "faults", "telefonie": "telephony",
    "offertes": "quotes", "wachtwoord": "password", "gewijzigd": "changed", "registreren": "register",
    "apparaat": "device", "beeldscherm": "monitor", "controle": "check", "eindklant": "end-customer",
    "klaar": "done", "opties": "options", "storing-bijlage": "fault-attachment", "storing-melden": "report-fault",
    "taal": "language", "inloggen": "login", "uitloggen": "logout", "wachtwoord-vergeten": "password-reset",
    "wachtwoord-instellen": "set-password", "vergelijken": "compare", "importeren": "import", "verslag": "report",
    "zoeken": "search", "rapportage": "reports",
}
# Old first parts that are redirected (the rest of an address is translated word by word).
TOP = ("beheer", "aanmelden", "factuur", "installatie", "database-bijwerken", "mijn", "registreren",
       "storing-bijlage", "storing-melden", "taal", "inloggen", "uitloggen", "wachtwoord-vergeten",
       "wachtwoord-instellen")
PATTERN = r"^(?P<old>" + "|".join(re.escape(t) for t in TOP) + r")(?P<rest>/.*)?$"


def translate(path):
    """'/mijn/bestellingen/12/' → '/my/orders/12/'. Addresses that do not start with an old part stay as they
    are; parts that are not words (numbers, codes) are kept."""
    lead = "/" if path.startswith("/") else ""
    parts = path.lstrip("/").split("/")
    if not parts or parts[0] not in TOP:
        return path
    if parts[0] == "wachtwoord-instellen" and len(parts) > 2 and parts[1] != "klaar":
        return lead + "/".join(["set-password", *parts[1:]])  # keep the reset code as it is
    return lead + "/".join(WORDS.get(p, p) for p in parts)


def redirect_old_address(request, old, rest=None):
    query = request.META.get("QUERY_STRING")
    new = translate("/" + old + (rest or "/"))
    response = HttpResponsePermanentRedirect(new + (f"?{query}" if query else ""))
    if request.method not in ("GET", "HEAD"):
        response.status_code = 308  # keep the method and the form data
    return response
