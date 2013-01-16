from mezzanine.forms.models import Form, Field

from modeltranslation.translator import TranslationOptions, translator


class FormTranslationOptions(TranslationOptions):
    fields = ("button_text", "response", "email_subject", "email_message")


class FieldTranslationOptions(TranslationOptions):
    fields = ("label", "choices", "default", "placeholder_text", "help_text")


translator.register(Form, FormTranslationOptions)
translator.register(Field, FieldTranslationOptions)
