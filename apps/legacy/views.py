"""Admin pages for comparing an external (previous webshop) database with PackDesk."""

import csv

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .compare import PARTS_BY_KEY, admin_link, compare_all, number_tops, search, show
from .connection import ExternalDatabaseError, open_reader
from .models import ExternalDatabase

CACHE_SECONDS = 30 * 60
CATEGORIES = {"only_old": gettext_lazy("Only in the old database"), "only_new": gettext_lazy("Only in PackDesk"),
              "different": gettext_lazy("Different")}


def _allowed(request):
    if not request.user.has_perm("legacy.compare_databases"):
        raise PermissionDenied


def _context(request, **extra):
    return {**admin.site.each_context(request), **extra}


def _cache_key(db):
    return f"packdesk:legacy-compare:{db.pk}:{db.updated_at.timestamp()}"


def _run(db):
    with open_reader(db) as reader:
        results = compare_all(reader)
        tops = number_tops(reader)
    data = {
        "compared_at": timezone.now(), "tops": tops,
        "parts": {r.part.key: {"summary": r.summary(), "only_old": r.only_old, "only_new": r.only_new,
                               "different": r.different} for r in results},
    }
    cache.set(_cache_key(db), data, CACHE_SECONDS)
    return data


def _data(request, db, refresh=False):
    data = None if refresh else cache.get(_cache_key(db))
    if data is None:
        try:
            data = _run(db)
        except ExternalDatabaseError as exc:
            messages.error(request, _("No connection with %(name)s: %(error)s") % {"name": db.name, "error": exc})
            return None
    return data


@staff_member_required
def choose(request):
    _allowed(request)
    databases = list(ExternalDatabase.objects.all())
    if len(databases) == 1:
        return redirect("legacy_compare", databases[0].pk)
    return render(request, "legacy/choose.html", _context(request, title=_("Compare databases"), databases=databases))


@staff_member_required
def overview(request, pk):
    _allowed(request)
    db = get_object_or_404(ExternalDatabase, pk=pk)
    if request.method == "POST":
        _data(request, db, refresh=True)
        return redirect("legacy_compare", db.pk)
    data = _data(request, db)
    return render(request, "legacy/overview.html", _context(
        request, title=_("Compare databases"), db=db, data=data,
        summaries=[p["summary"] for p in data["parts"].values()] if data else [],
    ))


def _rows(part, category, items):
    """Table rows for a list page and its CSV: (label, link, details)."""
    if category == "only_old":
        columns = [f.old for f in part.fields] or ["id"]
        return [(part.label_old(r), "", [(c, show(r.get(c))) for c in ["id", *columns] if c in r]) for r in items]
    if category == "only_new":
        return [(part.label_new(r), admin_link(part, r), []) for r in items]
    return [(part.label_old(old), admin_link(part, new), [(label, f"{a} → {b}") for label, a, b in diffs])
            for old, new, diffs in items]


@staff_member_required
def detail(request, pk, part_key, category):
    _allowed(request)
    db = get_object_or_404(ExternalDatabase, pk=pk)
    part = PARTS_BY_KEY.get(part_key)
    if part is None or category not in CATEGORIES:
        raise Http404
    data = _data(request, db)
    if data is None:
        return redirect("legacy_compare", db.pk)
    rows = _rows(part, category, data["parts"][part_key][category])
    if request.GET.get("format") == "csv":
        return _csv(part, category, rows)
    return render(request, "legacy/detail.html", _context(
        request, title=f"{part.label}: {CATEGORIES[category]}", db=db, part=part, category=category,
        category_label=CATEGORIES[category], rows=rows[:500], total=len(rows), data=data,
    ))


def _csv(part, category, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="compare-{part.key}-{category}.csv"'
    response.write("﻿")  # Excel recognises UTF-8
    writer = csv.writer(response, delimiter=";")
    writer.writerow([str(part.label), _("Details")])
    for label, _link, details in rows:
        writer.writerow([label, " | ".join(f"{k}: {v}" for k, v in details)])
    return response


@staff_member_required
def search_view(request, pk):
    _allowed(request)
    db = get_object_or_404(ExternalDatabase, pk=pk)
    q = request.GET.get("q", "").strip()
    results = []
    if len(q) >= 2:
        try:
            with open_reader(db) as reader:
                results = search(reader, q)
        except ExternalDatabaseError as exc:
            messages.error(request, _("No connection with %(name)s: %(error)s") % {"name": db.name, "error": exc})
    return render(request, "legacy/search.html", _context(request, title=_("Search in both databases"), db=db,
                                                          q=q, results=results))
