from modeltranslation.translator import TranslationOptions, register

from .models import FaultSettings, RepairOption


@register(RepairOption)
class RepairOptionTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(FaultSettings)
class FaultSettingsTranslationOptions(TranslationOptions):
    fields = ("intro", "office_hours_text", "thanks", "confirmation_subject", "confirmation_body")
