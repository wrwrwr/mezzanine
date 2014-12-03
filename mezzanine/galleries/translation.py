from mezzanine.galleries.models import Gallery, GalleryImage

from modeltranslation.translator import TranslationOptions, translator


class GalleryImageTranslationOptions(TranslationOptions):
    fields = ("description",)


translator.register(Gallery)
translator.register(GalleryImage, GalleryImageTranslationOptions)
