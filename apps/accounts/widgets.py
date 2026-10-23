from django import forms

from .permissions import ACTIONS, matrix_rows


class PermissionMatrixWidget(forms.CheckboxSelectMultiple):
    """Permissions as a table: one row per function, columns view / add / change / delete / other."""

    template_name = "accounts/permission_matrix.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        selected = {str(v) for v in (value or [])}
        permissions = list(self.choices.queryset)
        rows = []
        for app_name, model_name, standard, extras in matrix_rows(permissions):
            cells = [(code, standard.get(code)) for code, _label in ACTIONS]
            rows.append({"app": app_name, "model": model_name, "cells": cells, "extras": extras})
        context["widget"].update({"rows": rows, "actions": ACTIONS, "selected": selected})
        return context
