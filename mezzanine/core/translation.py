
from mezzanine.core.models import Slugged, MetaData, Displayable, RichText

from modeltranslation.translator import TranslationOptions, translator


class SluggedTranslationOptions(TranslationOptions):
    fields = ("title", "slug")


# Keywords are stored as separate ``Keyword`` models, connected with
# content through ``AssignedKeywords``. Searchable ``keywords_string``
# fields are only created on concrete subclasses.
class MetaDataTranslationOptions(TranslationOptions):
    fields = ("_meta_title", "description")


class DisplayableTranslationOptions(TranslationOptions):
    fields = ("short_url",)


class RichTextTranslationOptions(TranslationOptions):
    fields = ("content",)


translator.register(Slugged, SluggedTranslationOptions)
translator.register(MetaData, MetaDataTranslationOptions)
translator.register(Displayable, DisplayableTranslationOptions)
translator.register(RichText, RichTextTranslationOptions)
