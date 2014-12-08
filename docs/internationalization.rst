====================
Internationalization
====================

Mezzanine makes it possible to translate static and dynamic parts of your
website.  Static translations are possible thanks to Django's gettext
infrastructure [LINK] and content translation is based on modeltranslation
app [LINK].

Starting a multi-language project
=================================

0. Current branches:
        wrwrwr/modeltranslation@develop-1.7 (actually fix/test-update-command-3 at the moment...)
        wrwrwr/mezzanine/feature/modeltranslation-integration-1.7
1. mezzanine_project
2. settings.py: LANGUAGES, USE_I18N, USE_MODELTRANSLATION
3. urls.py: patterns --> i18n_patterns
4. createdb

Making fields translatable
==========================

1. register in translation.py
2. the same commands as with new languages

Adding new languages
====================

1. sync_translation_fields
2. update_translation_fields
3. resavemodels

Advanced commands and options
=============================

AUTO_POPULATION
MIGRATIONS_IGNORE
modeltranslations loaddata
