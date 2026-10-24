from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class TrashEntry(models.Model):
    """Something deleted in the admin, kept with everything that was deleted along with it."""

    deleted_at = models.DateTimeField(_("deleted at"), auto_now_add=True, db_index=True)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name=_("deleted by"))
    model = models.CharField(_("kind"), max_length=100, db_index=True)  # app_label.model_name
    kind = models.CharField(_("kind"), max_length=100)  # readable name at the time of deleting
    label = models.CharField(_("name"), max_length=300, db_index=True)
    object_count = models.PositiveIntegerField(_("items"), default=1)
    summary = models.TextField(_("deleted along with it"), blank=True)
    data = models.TextField(editable=False)  # serialized objects, in the order to restore them
    field_updates = models.TextField(editable=False, default="[]")  # links set to empty by the deletion

    class Meta:
        verbose_name = _("deleted item")
        verbose_name_plural = _("trash")
        ordering = ["-deleted_at"]
        permissions = [("restore_trashentry", _("Can restore deleted items"))]

    def __str__(self):
        return f"{self.kind}: {self.label}"
