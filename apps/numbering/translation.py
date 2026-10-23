from modeltranslation.translator import TranslationOptions, register

from .models import NumberSequence


@register(NumberSequence)
class NumberSequenceTranslationOptions(TranslationOptions):
    fields = ("name",)
