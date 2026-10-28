from modeltranslation.translator import TranslationOptions, register

from .models import Condition, DeliveryOption, DeviceType, HardwareSettings, Specification


@register(HardwareSettings)
class HardwareSettingsTranslationOptions(TranslationOptions):
    fields = ("intro", "terms_text")


@register(DeviceType)
class DeviceTypeTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Specification)
class SpecificationTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Condition)
class ConditionTranslationOptions(TranslationOptions):
    fields = ("name", "description")


@register(DeliveryOption)
class DeliveryOptionTranslationOptions(TranslationOptions):
    fields = ("name",)
