from modeltranslation.translator import TranslationOptions, register

from .models import HomeBlock, MenuItem, SiteSettings


@register(SiteSettings)
class SiteSettingsTranslationOptions(TranslationOptions):
    fields = (
        "tagline",
        "intro_text",
        "meta_description",
        "hero_button_text",
        "footer_text",
        "maintenance_message",
        "announcement_text",
    )


@register(HomeBlock)
class HomeBlockTranslationOptions(TranslationOptions):
    fields = ("title", "text", "link_text")


@register(MenuItem)
class MenuItemTranslationOptions(TranslationOptions):
    fields = ("label",)
