from __future__ import print_function

from optparse import make_option

from django.core.management.base import NoArgsCommand
from django.db.models import get_models

from mezzanine.core.models import Slugged, MetaData
from mezzanine.pages.models import Page
from mezzanine.utils.translation import for_all_languages


class Command(NoArgsCommand):
    option_list = NoArgsCommand.option_list + (
        make_option("--reset_slugs", action="store_true", default=False,
            help=("With \"reset_slugs\" argument it will reset all slugs, "
                  "allowing them to be regenerated automatically (albeit, "
                  "forefeiting any customizations!). May need to be run a "
                  "few times to get all path chains sound.")),)
    help = ("Loads and saves all models that have some fields generated "
            "automatically (slugs, descriptions, titles) to let them "
            "generate values for new languages.")

    def handle_noargs(self, **options):
        verbosity = int(options.get("verbosity", 0))
        reset_slugs = options.get("reset_slugs")

        for model in get_models():
            if reset_slugs and issubclass(model, Slugged):
                if verbosity > 1:
                    print("Resetting slugs of %s" % model.__name__)
                for instance in model.objects.all():
                    def reset_slug():
                        instance.slug = None
                    for_all_languages(reset_slug)
                    instance.save()

            if issubclass(model, (Slugged, MetaData, Page)):
                if verbosity > 1:
                    print("Updating %s" % model.__name__)
                for instance in model.objects.all():
                    instance.save()
