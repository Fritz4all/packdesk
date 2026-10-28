from modeltranslation.translator import TranslationOptions, register

from .models import RoleInfo


@register(RoleInfo)
class RoleInfoTranslation(TranslationOptions):
    fields = ("title",)
