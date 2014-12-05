
from __future__ import print_function, unicode_literals
from future.builtins import input

from socket import gethostname

from django import VERSION
from django.conf import settings
from django.contrib.auth import models as auth_app
from django.contrib.sites.models import Site
from django.contrib.sites.management import create_default_site
from django.contrib.sites import models as sites_app
from django.core.management import call_command
from django.db.models.signals import post_syncdb

from mezzanine.utils.models import get_user_model
from mezzanine.utils.tests import copy_test_to_media


User = get_user_model()

DEFAULT_USERNAME = "admin"
DEFAULT_EMAIL = "example@example.com"
DEFAULT_PASSWORD = "default"


def check_created(created, *required):
    """
    Checks the given models were created inside a ``post_syncdb``
    signal for Django 1.6 or lower, so that we can install initial
    data. For Django 1.7 and greater, this can always retrun True.
    """
    return VERSION >= (1, 7) or set(required).issubset(set(created))


def create_user(app, created_models, verbosity, interactive, **kwargs):
    if (settings.DEBUG and check_created(created_models, User)
            and not interactive):
        if User.objects.count() > 0:
            return
        if verbosity >= 1:
            print()
            print("Creating default account (username: %s / password: %s) ..."
                  % (DEFAULT_USERNAME, DEFAULT_PASSWORD))
            print()
        args = (DEFAULT_USERNAME, DEFAULT_EMAIL, DEFAULT_PASSWORD)
        User.objects.create_superuser(*args)


def is_full_install():
    for app in ["forms", "galleries", "blog", "pages"]:
        if "mezzanine.%s" % app not in settings.INSTALLED_APPS:
            return False
    return True


def create_pages(app, created_models, verbosity, interactive, **kwargs):

    if not is_full_install():
        return

    from mezzanine.pages.models import Page
    from mezzanine.forms.models import Form
    from mezzanine.galleries.models import Gallery

    if check_created(created_models, Page, Form, Gallery):
        call_command("loaddata", "mezzanine_required.json")
        if interactive:
            confirm = input("\nWould you like to install some initial "
                              "demo pages?\nEg: About us, Contact form, "
                              "Gallery. (yes/no): ")
            while confirm not in ("yes", "no"):
                confirm = input("Please enter either 'yes' or 'no': ")
            if confirm == "yes":
                install_optional_data(verbosity)
        if settings.USE_MODELTRANSLATION:
            # Initial data fixtures have slugs only for one languague, not
            # necessarily loaded for the default one.
            # TODO: We should quite likely auto-run ``makemigrations`` and
            #       ``migrate`` here -- you can't generate the translated
            #       slugs until the fields are created. However, at the
            #       moment of writing, the required/optional content is not
            #       loaded with 1.7 -- ``created_models`` does not contain
            #       models created for "migrated" apps.
            call_command("resavemodels", verbosity)


def create_site(app, created_models, verbosity, interactive, **kwargs):
    if check_created(created_models, Site):
        domain = "127.0.0.1:8000" if settings.DEBUG else gethostname()
        if interactive:
            entered = input("\nA site record is required.\nPlease "
                                "enter the domain and optional port in "
                                "the format 'domain:port'.\nFor example "
                                "'localhost:8000' or 'www.example.com'. "
                                "\nHit enter to use the default (%s): " %
                                domain)
            if entered:
                domain = entered.strip("': ")
        if verbosity >= 1:
            print()
            print("Creating default site record: %s ... " % domain)
            print()
        try:
            site = Site.objects.get()
        except Site.DoesNotExist:
            site = Site()
        site.name = "Default"
        site.domain = domain
        site.save()


def install_optional_data(verbosity):
    if not is_full_install():
        return
    if verbosity >= 1:
        print()
        print("Creating demo pages: About us, Contact form, Gallery ...")
        print()
    from mezzanine.galleries.models import Gallery
    call_command("loaddata", "mezzanine_optional.json")
    zip_name = "gallery.zip"
    copy_test_to_media("mezzanine.core", zip_name)
    gallery = Gallery.objects.get()
    gallery.zip_import = zip_name
    gallery.save()


if not settings.TESTING:
    post_syncdb.connect(create_user, sender=auth_app)
    if "mezzanine.pages" in settings.INSTALLED_APPS:
        from mezzanine.pages import models as pages_app
        post_syncdb.connect(create_pages, sender=pages_app)
    post_syncdb.connect(create_site, sender=sites_app)
    post_syncdb.disconnect(create_default_site, sender=sites_app)
