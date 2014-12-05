from django.core.management.base import NoArgsCommand
from django.db.models import get_models


class Command(NoArgsCommand):
    help = ("Resaves all models that have resave_models class attribute set. "
            "Some fields are auto-generated on model save (such as slugs, "
            "descriptions, titles) resaving models lets them fill in missing "
            "values.")

    def handle_noargs(self, **options):
        verbosity = int(options.get("verbosity", 0))

        for model in get_models():
            if getattr(model, "resave_models", False):
                if verbosity > 1:
                    print("Resaving %s" % model.__name__)
                for instance in model.objects.all():
                    instance.save()
