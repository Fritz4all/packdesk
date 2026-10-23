from modeltranslation.translator import TranslationOptions, register

from .models import Category, HardwareClass, LicenceSettings, OptionType, SupportPack, SupportService, Vendor


@register(Category)
class CategoryTranslationOptions(TranslationOptions):
    fields = ("name", "explanation")


@register(HardwareClass)
class HardwareClassTranslationOptions(TranslationOptions):
    fields = ("name", "explanation")


@register(OptionType)
class OptionTypeTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(SupportService)
class SupportServiceTranslationOptions(TranslationOptions):
    fields = ("name", "response")


@register(SupportPack)
class SupportPackTranslationOptions(TranslationOptions):
    fields = ("description",)


@register(Vendor)
class VendorTranslationOptions(TranslationOptions):
    fields = ("product_nr_help",)


@register(LicenceSettings)
class LicenceSettingsTranslationOptions(TranslationOptions):
    fields = ("wizard_intro", "wizard_done", "contact_text")
