
from mezzanine.core.models import Slugged, MetaData, RichText

from modeltranslation.translator import TranslationOptions, translator


class SluggedTranslationOptions(TranslationOptions):
    fields = ("title", "slug")


class MetaDataTranslationOptions(TranslationOptions):
    fields = ("_meta_title", "description") #, "keywords")


class RichTextTranslationOptions(TranslationOptions):
    fields = ("content",)


translator.register(Slugged, SluggedTranslationOptions)
translator.register(MetaData, MetaDataTranslationOptions)
translator.register(RichText, RichTextTranslationOptions)
