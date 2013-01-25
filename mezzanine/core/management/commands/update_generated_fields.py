
from django.core.management.base import NoArgsCommand
from django.db.models import get_models

from mezzanine.core.models import Slugged, MetaData
from mezzanine.pages.models import Page


class Command(NoArgsCommand):

    help = ("Loads and saves all models that have some fields generated"
            " automatically (slugs, descriptions, titles) to let them"
            " generate values for new languages.")

    def handle_noargs(self, **options):
        verbosity = int(options.get("verbosity", 0))

        for model in get_models():
            if issubclass(model, (Slugged, MetaData, Page)):
                if verbosity > 0:
                    print "Updating %s" % model.__name__
                for instance in model.objects.all():
                    instance.save()
