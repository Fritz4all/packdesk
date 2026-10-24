from modeltranslation.translator import TranslationOptions, register

from .models import InvoiceSettings


@register(InvoiceSettings)
class InvoiceSettingsTranslationOptions(TranslationOptions):
    fields = ("payment_text", "notice_text", "footer_text", "email_subject", "email_body")
