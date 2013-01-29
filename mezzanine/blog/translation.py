from mezzanine.blog.models import BlogPost, BlogCategory

from modeltranslation.translator import TranslationOptions, translator


class BlogPostTranslationOptions(TranslationOptions):
    fields = ("keywords_string",)


translator.register(BlogPost, BlogPostTranslationOptions)
translator.register(BlogCategory)
