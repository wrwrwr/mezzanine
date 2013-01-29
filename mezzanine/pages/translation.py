from mezzanine.pages.models import Page, RichTextPage, Link

from modeltranslation.translator import TranslationOptions, translator


class PageTranslationOptions(TranslationOptions):
    fields = ("titles", "keywords_string")


translator.register(Page, PageTranslationOptions)
translator.register((RichTextPage, Link,))


# Titles is only generated on save. Opt-in for the resavemodels command.
Page.resavemodels_command = True
