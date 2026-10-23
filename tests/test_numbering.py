import datetime
import random

import pytest
from django.core.exceptions import ValidationError

from apps.numbering import patterns
from apps.numbering.admin_badge import problems
from apps.numbering.checks import check
from apps.numbering.models import CounterChange, GapNote, NumberSequence

from .conftest import make_user

URL = "/beheer/numbering/numbersequence/"


@pytest.fixture
def archive(tmp_path, settings):
    settings.DOCUMENT_ARCHIVE_DIR = str(tmp_path)

    def add(*numbers):
        for n in numbers:
            (tmp_path / f"invoice_{n:010d}.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "notes.txt").write_text("not an invoice")

    return add


@pytest.fixture
def invoices(db):
    return NumberSequence.objects.get(key="invoice")


# --- patterns ----------------------------------------------------------------

def test_render_patterns():
    day = datetime.date(2026, 3, 7)
    assert patterns.render("{nr}", 42, day) == "42"
    assert patterns.render("F{year}-{nr:5}", 42, day) == "F2026-00042"
    assert patterns.render("{yy}{month}/{nr}", 7, day) == "2603/7"
    assert patterns.render("WS{nr}{letters:2}", 17001, day, random.Random(1))[:7] == "WS17001"


def test_validate_patterns():
    patterns.validate("F{year}-{nr:5}")
    with pytest.raises(patterns.PatternError):
        patterns.validate("F{year}")
    with pytest.raises(patterns.PatternError):
        patterns.validate("{nr}{foo}")


def test_number_from_formatted_value():
    assert patterns.number_from("F{year}-{nr:5}", "F2026-00042") == 42
    assert patterns.number_from("WS{nr}{letters:2}", "WS17001QX") == 17001
    assert patterns.number_from("F{year}-{nr:5}", "something else") is None


def test_default_sequences_exist(db):
    keys = set(NumberSequence.objects.values_list("key", flat=True))
    assert {"invoice", "quote", "order", "licence", "customer", "ticket"} <= keys


# --- issuing -----------------------------------------------------------------

def test_issue_counts_up(invoices):
    invoices.pattern = "F{nr:4}"
    invoices.next_number = 9
    invoices.save()
    assert NumberSequence.issue("invoice") == (9, "F0009")
    assert NumberSequence.issue("invoice") == (10, "F0010")
    invoices.refresh_from_db()
    assert invoices.next_number == 11


def test_yearly_reset(invoices):
    invoices.reset_yearly = True
    invoices.current_year = 2000
    invoices.next_number = 500
    invoices.save()
    number, _formatted = NumberSequence.issue("invoice")
    assert number == 1


# --- checks against the archive --------------------------------------------------

def test_check_in_order(invoices, archive):
    archive(1, 2, 3)
    invoices.next_number = 4
    invoices.save()
    result = check(invoices)
    assert (result.status, result.count, result.highest, result.gaps) == ("ok", 3, 3, [])
    assert not result.has_problem


def test_check_counter_too_low(invoices, archive):
    archive(1, 2, 3)
    result = check(invoices)
    assert result.status == "behind" and result.has_problem and result.suggested_next == 4


def test_check_finds_gaps_in_the_middle(invoices, archive):
    archive(1, 2, 6, 8, 9)
    invoices.next_number = 10
    invoices.save()
    result = check(invoices)
    assert result.gaps == [(3, 5), (7, 7)] and result.missing_count == 4


def test_check_finds_removed_last_document(invoices, archive):
    archive(1, 2, 3)
    invoices.next_number = 6  # 4 and 5 were handed out, their files are gone
    invoices.save()
    result = check(invoices)
    assert result.status == "ahead" and result.gaps == [(4, 5)]


def test_explained_gap_is_no_longer_a_problem(invoices, archive):
    archive(1, 2, 6)
    invoices.next_number = 7
    invoices.save()
    GapNote.objects.create(sequence=invoices, first=3, last=4, reason="Geannuleerd voor verzending")
    result = check(invoices)
    assert result.gaps == [(5, 5)]
    GapNote.objects.create(sequence=invoices, first=5, last=5, reason="Testfactuur verwijderd")
    assert not check(invoices).has_problem


def test_without_archive_nothing_is_compared(invoices, settings):
    settings.DOCUMENT_ARCHIVE_DIR = ""
    result = check(invoices)
    assert result.status == "empty" and not result.source_available


# --- corrections -------------------------------------------------------------

def test_correct_logs_change(invoices, archive):
    archive(1, 2, 3)
    user = make_user("fin@example.test", staff=True, role="Financieel")
    invoices.correct(4, user, "Gelijkgezet met archief", highest_issued=3)
    change = CounterChange.objects.get(sequence=invoices)
    assert (change.old_value, change.new_value, change.user, change.reason) == (1, 4, user, "Gelijkgezet met archief")


def test_correct_never_below_issued(invoices):
    with pytest.raises(ValidationError):
        invoices.correct(3, None, "fout", highest_issued=3)


def admin_form(**extra):
    data = {"name_nl": "Facturen", "name_en": "Invoices", "name_de": "Rechnungen", "pattern": "{nr}",
            "archive_regex": r"invoice_(\d+)\.pdf"}
    for prefix in ("gap_notes", "changes"):
        data.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0",
                     f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "1000"})
    data.update(extra)
    return data


def test_admin_correction_requires_reason_and_valid_number(client, site, invoices, archive):
    archive(10, 11)
    client.force_login(make_user("fin@example.test", staff=True, role="Financieel"))
    response = client.post(f"{URL}{invoices.pk}/change/", admin_form(new_next_number="12"))
    assert response.status_code == 200  # reason missing
    response = client.post(f"{URL}{invoices.pk}/change/", admin_form(new_next_number="5", correction_reason="x"))
    assert response.status_code == 200  # below issued numbers
    response = client.post(f"{URL}{invoices.pk}/change/", admin_form(new_next_number="12", correction_reason="Archief"))
    assert response.status_code == 302, response.content.decode()[:2000]
    invoices.refresh_from_db()
    assert invoices.next_number == 12


def test_set_to_highest_action(client, site, invoices, archive):
    archive(1017494, 1030953)
    client.force_login(make_user("fin@example.test", staff=True, role="Financieel"))
    client.post(f"{URL}{invoices.pk}/action/set-to-highest/")
    invoices.refresh_from_db()
    assert invoices.next_number == 1030954
    assert CounterChange.objects.filter(sequence=invoices, new_value=1030954).exists()


def test_gap_note_records_user(client, site, invoices, archive):
    archive(1, 3)
    invoices.next_number = 4
    invoices.save()
    user = make_user("fin@example.test", staff=True, role="Financieel")
    client.force_login(user)
    data = admin_form(**{"gap_notes-TOTAL_FORMS": "1", "gap_notes-0-first": "2", "gap_notes-0-last": "2",
                         "gap_notes-0-reason": "Nooit verstuurd"})
    assert client.post(f"{URL}{invoices.pk}/change/", data).status_code == 302
    assert GapNote.objects.get(sequence=invoices).created_by == user


def test_employee_cannot_correct(client, site, invoices):
    client.force_login(make_user("mw@example.test", staff=True, role="Medewerker"))
    assert client.get(f"{URL}{invoices.pk}/change/").status_code == 403
    assert client.post(f"{URL}{invoices.pk}/action/set-to-highest/").status_code == 403


def test_status_shown_in_admin_and_badge(client, site, invoices, archive, rf):
    archive(1, 2, 4)
    user = make_user("fin@example.test", staff=True, role="Financieel")
    client.force_login(user)
    page = client.get(f"{URL}{invoices.pk}/change/").content.decode()
    assert "1 / 4" in page and ">3<" in page.replace(" ", "")
    request = rf.get("/")
    request.user = user
    assert problems(request) == "1"


def test_block_token_like_old_licence_numbers():
    day = datetime.date(2026, 1, 5)
    assert patterns.render("{yy}{block:4}", 1, day) == "26A0001"
    assert patterns.render("{yy}{block:4}", 10000, day) == "26B0000"
    assert patterns.number_from("{yy}{block:4}", "26B0007") == 10007
    patterns.validate("{yy}{block:4}")
