from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import patterns


class NumberSequence(models.Model):
    """A counter for one kind of document: invoices, quotes, orders, licences, ...

    Numbers are handed out inside a database transaction, so two users can
    never get the same number. A number that was handed out is never reused.
    """

    key = models.SlugField(_("code"), unique=True, help_text=_("Internal code used by the software, e.g. invoice."))
    name = models.CharField(_("name"), max_length=100)
    pattern = models.CharField(
        _("pattern"),
        max_length=60,
        default="{nr}",
        help_text=_("{nr} = counter, {nr:5} = counter with 5 digits, {year}, {yy}, {month}, {letters:2} = random letters."),
    )
    next_number = models.PositiveBigIntegerField(_("next number"), default=1)
    reset_yearly = models.BooleanField(_("start again every year"), default=False)
    current_year = models.PositiveSmallIntegerField(_("year of counter"), null=True, blank=True, editable=False)
    archive_regex = models.CharField(
        _("file names in archive"),
        max_length=120,
        blank=True,
        help_text=_(
            "Optional. Regular expression for documents in the archive folder; the first group is the number, "
            r"e.g. invoice_(\d+)\.pdf"
        ),
    )

    class Meta:
        verbose_name = _("number sequence")
        verbose_name_plural = _("number sequences")
        ordering = ["name"]
        permissions = [("correct_numbersequence", _("Can correct number counters"))]

    def __str__(self):
        return self.name

    def clean(self):
        try:
            patterns.validate(self.pattern)
        except patterns.PatternError as exc:
            raise ValidationError({"pattern": str(exc)})

    def format(self, number, when=None):
        return patterns.render(self.pattern, number, when or timezone.localdate())

    def preview(self):
        return self.format(self._number_for_today())

    def _number_for_today(self):
        if self.reset_yearly and self.current_year and self.current_year != timezone.localdate().year:
            return 1
        return self.next_number

    @classmethod
    def issue(cls, key):
        """Hand out the next number of sequence `key`; returns (counter, formatted number)."""
        with transaction.atomic():
            seq = cls.objects.select_for_update().get(key=key)
            today = timezone.localdate()
            if seq.reset_yearly and seq.current_year != today.year:
                seq.next_number = 1 if seq.current_year else seq.next_number
                seq.current_year = today.year
            number = seq.next_number
            seq.next_number = number + 1
            seq.save(update_fields=["next_number", "current_year"])
            return number, seq.format(number, today)

    def correct(self, new_next, user, reason, highest_issued=None):
        """Set the counter by hand. It may never go back to a number that was already issued."""
        if highest_issued is not None and new_next <= highest_issued:
            raise ValidationError(
                _("The next number must be higher than %(highest)s, the highest number already issued.")
                % {"highest": highest_issued}
            )
        with transaction.atomic():
            seq = NumberSequence.objects.select_for_update().get(pk=self.pk)
            old = seq.next_number
            seq.next_number = new_next
            seq.save(update_fields=["next_number"])
            CounterChange.objects.create(sequence=seq, user=user, old_value=old, new_value=new_next, reason=reason)
        self.next_number = new_next


class CounterChange(models.Model):
    """Log of every manual change to a counter."""

    sequence = models.ForeignKey(NumberSequence, on_delete=models.CASCADE, related_name="changes")
    changed_at = models.DateTimeField(_("changed at"), auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name=_("by"))
    old_value = models.PositiveBigIntegerField(_("old next number"))
    new_value = models.PositiveBigIntegerField(_("new next number"))
    reason = models.TextField(_("reason"))

    class Meta:
        verbose_name = _("counter change")
        verbose_name_plural = _("counter changes")
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.old_value} → {self.new_value}"


class GapNote(models.Model):
    """Explains missing numbers, e.g. an invoice that was cancelled before sending.

    An explained gap is no longer reported as a problem.
    """

    sequence = models.ForeignKey(NumberSequence, on_delete=models.CASCADE, related_name="gap_notes")
    first = models.PositiveBigIntegerField(_("from number"))
    last = models.PositiveBigIntegerField(_("to number"))
    reason = models.TextField(_("explanation"))
    created_at = models.DateTimeField(_("recorded at"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("by")
    )

    class Meta:
        verbose_name = _("explained gap")
        verbose_name_plural = _("explained gaps")
        ordering = ["first"]

    def __str__(self):
        return f"{self.first}" if self.first == self.last else f"{self.first}–{self.last}"

    def clean(self):
        if self.first is not None and self.last is not None and self.last < self.first:
            raise ValidationError({"last": _("Must be at least the first number.")})

    def covers(self, number):
        return self.first <= number <= self.last
