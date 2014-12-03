
from mezzanine.pages.models import Page, RichTextPage, Link

from modeltranslation.translator import TranslationOptions, translator


class PageTranslationOptions(TranslationOptions):
    fields = ("titles", "keywords_string")


translator.register(Page, PageTranslationOptions)
translator.register((RichTextPage, Link,))
