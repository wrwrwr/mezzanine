from __future__ import unicode_literals

from django.contrib import admin

from mezzanine.core.admin import (TabularDynamicInlineAdmin,
                                  TranslationInlineModelAdmin)
from mezzanine.pages.admin import PageAdmin
from mezzanine.galleries.models import Gallery, GalleryImage


class GalleryImageInline(TabularDynamicInlineAdmin,
                         TranslationInlineModelAdmin):
    model = GalleryImage


class GalleryAdmin(PageAdmin):

    class Media:
        css = {"all": ("mezzanine/css/admin/gallery.css",)}

    inlines = (GalleryImageInline,)


admin.site.register(Gallery, GalleryAdmin)
