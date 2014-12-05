from mezzanine.conf.models import Setting

from modeltranslation.translator import TranslationOptions, translator


class SettingTranslationOptions(TranslationOptions):
    fields = ("value",)


translator.register(Setting, SettingTranslationOptions)
