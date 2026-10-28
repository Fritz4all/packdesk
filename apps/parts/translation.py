from modeltranslation.translator import TranslationOptions, register

from .models import DeliveryTime, PartsSettings


@register(PartsSettings)
class PartsSettingsTranslationOptions(TranslationOptions):
    fields = ("intro", "terms_text")


@register(DeliveryTime)
class DeliveryTimeTranslationOptions(TranslationOptions):
    fields = ("name",)

