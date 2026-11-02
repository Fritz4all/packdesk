from modeltranslation.translator import TranslationOptions, register

from .models import ItemProperty, ItemType


@register(ItemType)
class ItemTypeTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ItemProperty)
class ItemPropertyTranslationOptions(TranslationOptions):
    fields = ("name",)
