from mezzanine.twitter.models import Query

from modeltranslation.translator import TranslationOptions, translator


class QueryTranslationOptions(TranslationOptions):
    fields = ("value",)


translator.register(Query, QueryTranslationOptions)
