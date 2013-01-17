
from contextlib import contextmanager

from django.utils.translation import activate, get_language

from mezzanine.conf import settings


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
        # Override the modeltranslation setting and restore it after
        # executing the wrapped block.
        from modeltranslation import settings as mt_settings
        current_enable_fallbacks = mt_settings.ENABLE_FALLBACKS
        mt_settings.ENABLE_FALLBACKS = False
        try:
            yield
        finally:
            mt_settings.ENABLE_FALLBACKS = current_enable_fallbacks
    else:
        # Just execute the code if content translation is not used.
        yield
