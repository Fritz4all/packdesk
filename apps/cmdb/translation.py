from modeltranslation.translator import TranslationOptions, register

from .models import CmdbSettings, ItemField, ItemStatus, ItemType, RelationKind


@register(ItemType)
class ItemTypeTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ItemField)
class ItemFieldTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ItemStatus)
class ItemStatusTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(RelationKind)
class RelationKindTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(CmdbSettings)
class CmdbSettingsTranslationOptions(TranslationOptions):
    fields = ("warranty_subject", "warranty_body")
