from modeltranslation.translator import TranslationOptions, register

from .models import Country, CustomerType, SignupSettings


@register(CustomerType)
class CustomerTypeTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Country)
class CountryTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(SignupSettings)
class SignupSettingsTranslationOptions(TranslationOptions):
    fields = ("menu_label", "title", "intro", "thanks", "activation_subject", "activation_body")
