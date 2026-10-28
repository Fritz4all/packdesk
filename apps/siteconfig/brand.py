"""PackDesk's own icon: a service ticket with a check mark in a round badge, in a colour chosen under
Settings → Branding. Used as favicon, app icon and admin icon as long as no own favicon is uploaded.

The icon is drawn twice from the same coordinates (64 × 64): as SVG for browsers, and with Pillow as PNG/ICO
for places that need pixels (older browsers, phone home screens). Below 24 px only the check mark is drawn;
the ticket outline would be a blur at that size.
"""

import io

from django.utils.translation import gettext_lazy as _

COLORS = {
    "blue": ("#2563eb", _("Blue")),
    "purple": ("#7c3aed", _("Purple")),
    "teal": ("#0f766e", _("Teal")),
    "green": ("#15803d", _("Green")),
    "orange": ("#ea580c", _("Orange")),
    "pink": ("#db2777", _("Pink")),
    "slate": ("#334155", _("Slate")),
}
DEFAULT = "blue"
PRIMARY = "primary"  # the website's primary colour
CHOICES = [(key, label) for key, (_hex, label) in COLORS.items()] + [(PRIMARY, _("Primary colour of the website"))]
PNG_SIZES = (16, 32, 48, 180, 192, 512)

TICKET = ("M16 18 H48 a4 4 0 0 1 4 4 V27 a5 5 0 0 0 0 10 V42 a4 4 0 0 1 -4 4 H16 a4 4 0 0 1 -4 -4 V37 "
          "a5 5 0 0 0 0 -10 V22 a4 4 0 0 1 4 -4 Z")


def color(site):
    """The icon colour (#rrggbb) for these site settings."""
    choice = getattr(site, "icon_color", DEFAULT) or DEFAULT
    if choice == PRIMARY:
        return site.primary_color or COLORS[DEFAULT][0]
    return COLORS.get(choice, COLORS[DEFAULT])[0]


def svg(fill, small=False):
    """The icon as SVG text; `small` is the simplified one for 16 px."""
    if small:
        inner = ('<path d="M20 33 L29 42 L45 23" fill="none" stroke="#fff" stroke-width="9" '
                 'stroke-linecap="round" stroke-linejoin="round"/>')
    else:
        inner = (f'<path d="{TICKET}" fill="#fff"/><path d="M23 32 L29.5 38.5 L41 26" fill="none" stroke="{fill}" '
                 'stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="32" cy="32" r="32" '
            f'fill="{fill}"/>{inner}</svg>')


def _rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def _image(fill, size):
    """The icon drawn with Pillow, at 8× and scaled down for smooth edges."""
    from PIL import Image, ImageDraw

    scale = 8 * size / 64
    big = Image.new("RGBA", (round(64 * scale), round(64 * scale)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    p = lambda *xy: [round(v * scale) for v in xy]  # noqa: E731
    colour = _rgb(fill)
    draw.ellipse(p(0, 0, 64, 64), fill=colour)

    def check(points, width, ink):
        draw.line([tuple(p(*pt)) for pt in points], fill=ink, width=round(width * scale), joint="curve")
        for x, y in (points[0], points[-1]):  # round line ends
            r = width * scale / 2
            draw.ellipse([x * scale - r, y * scale - r, x * scale + r, y * scale + r], fill=ink)

    if size < 24:
        check([(20, 33), (29, 42), (45, 23)], 9, (255, 255, 255))
    else:
        white = (255, 255, 255)
        draw.rounded_rectangle(p(12, 18, 52, 46), radius=round(4 * scale), fill=white)
        for cx in (12, 52):  # the notches on both sides
            draw.ellipse(p(cx - 5, 27, cx + 5, 37), fill=colour)
        check([(23, 32), (29.5, 38.5), (41, 26)], 5, colour)
    return big.resize((size, size), Image.LANCZOS)


def png(fill, size):
    out = io.BytesIO()
    _image(fill, size).save(out, "PNG")
    return out.getvalue()


def ico(fill):
    out = io.BytesIO()
    images = [_image(fill, s) for s in (16, 32, 48)]
    images[-1].save(out, "ICO", sizes=[(16, 16), (32, 32), (48, 48)], append_images=images[:-1])
    return out.getvalue()
