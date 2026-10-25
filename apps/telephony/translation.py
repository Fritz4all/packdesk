from modeltranslation.translator import TranslationOptions, register

from .models import Category, Item, TelephonySettings


@register(TelephonySettings)
class TelephonySettingsTranslationOptions(TranslationOptions):
    fields = ("intro", "terms_text")


@register(Category)
class CategoryTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Item)
class ItemTranslationOptions(TranslationOptions):
    fields = ("name", "description")
