from django.core.management.base import NoArgsCommand
from django.db.models import get_models


class Command(NoArgsCommand):
    help = ("Resaves all models that have some fields auto-generated on model "
            "save (such as slugs, descriptions, titles) to let them set values "
            "for new languages.")

    def handle_noargs(self, **options):
        verbosity = int(options.get("verbosity", 0))

        for model in get_models():
            generated_fields = getattr(model, "generated_fields", [])
            if generated_fields:
                if verbosity > 1:
                    print("Updating %s" % model.__name__)
                for instance in model.objects.all():
                    instance.save()
