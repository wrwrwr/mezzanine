
from contextlib import contextmanager

from django.utils.translation import activate, get_language

from mezzanine.conf import settings


def patch_trans_null():
    """
    Allows changing the current language with Django's I18N disabled.

    Functions from Django's ``trans_null`` (used when USE_I18N is false)
    do more or less nothing. To allow content translation to work without
    enabling the static translation machinery we need the language set by
    ``activate`` to be returned by following ``get_language()`` calls.

    TODO: That's a potential candidate for a Django ticket.
    """
    from django.utils.translation import _trans

    def activate(language):
        _trans.active_language = language

    def get_language():
        return _trans.active_language

    _trans.active_language = settings.LANGUAGE_CODE
    _trans.activate = activate
    _trans.get_language = get_language


if settings.USE_MODELTRANSLATION and not settings.USE_I18N:
    patch_trans_null()


def for_all_languages(function):
    """
    Executes ``function`` once for each of the available languages.

    Example:

        def update_titles():
            page.titles = parent.titles + ' / ' + page.title
        for_all_languages(update_titles):

    Should be used when a translatable derived attribute is computed (field
    attributes tranparently refer / update translation fields for the active
    language).
    """
    if settings.USE_MODELTRANSLATION:
        # Activate each language and execute the wrapped code, making sure
        # to restore the current language in the end.
        from modeltranslation.settings import AVAILABLE_LANGUAGES
        current_language = get_language()
        try:
            for language in AVAILABLE_LANGUAGES:
                activate(language)
                function()
        finally:
            activate(current_language)
    else:
        # Fall back gracefully if content translation is disabled.
        function()


@contextmanager
def disable_fallbacks():
    """
    Temporarily disables language fallbacks, allowing to get translation
    fields values for the active language only.

    Example:

        activate(lang)
        with disable_fallbacks():
            lang_has_slug = bool(self.slug)

    May be used when you need to know if there is a non-empty value
    for a particular language.
    """
    if settings.USE_MODELTRANSLATION:
        from modeltranslation.utils import fallbacks
        with fallbacks(False):
            yield
    else:
        # Just execute the code if content translation is not used.
        yield
