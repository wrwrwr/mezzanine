from __future__ import unicode_literals
from future.builtins import int

from collections import defaultdict

from django import forms
from django import settings
from django.utils.safestring import mark_safe
from django.utils.translation import (get_language, override,
                                      ugettext_lazy as _)
from django.template.defaultfilters import urlize

from mezzanine.conf import settings, registry
from mezzanine.conf.models import Setting
from mezzanine.utils.translation import for_all_languages


FIELD_TYPES = {
    bool: forms.BooleanField,
    int: forms.IntegerField,
    float: forms.FloatField,
}


class SettingsForm(forms.Form):
    """
    Form for settings - creates a field for each setting in
    ``mezzanine.conf`` that is marked as editable.
    """

    def __init__(self, *args, **kwargs):
        super(SettingsForm, self).__init__(*args, **kwargs)
        settings.use_editable()
        # Create a form field for each editable setting from its type.
        for name in sorted(registry.keys()):
            setting = registry[name]
            if setting["editable"]:
                field_class = FIELD_TYPES.get(setting["type"], forms.CharField)
                kwargs = {
                    "label": setting["label"] + ":",
                    "required": setting["type"] in (int, float),
                    "initial": getattr(settings, name),
                    "help_text": self.format_help(setting["description"]),
                }
                if setting["choices"]:
                    field_class = forms.ChoiceField
                    kwargs["choices"] = setting["choices"]
                css_class = field_class.__name__.lower()

                def create_field():
                    field_name = name + "_" + get_language()
                    self.fields[field_name] = field_class(**kwargs)
                    self.fields[field_name].widget.attrs["class"] = css_class
                if setting["translatable"]:
                    for_all_languages(create_field)
                else:
                    if settings.USE_MODELTRANSLATION:
                        # Save value as the default translation for non-translatable
                        # settings with modeltranslation enabled.
                        from modeltranslation.settings import DEFAULT_LANGUAGE
                        override(DEFAULT_LANGUAGE:
                            create_field()
                    else:
                        create_field()

    def __iter__(self):
        """
        Calculate and apply a group heading to each field and order by the
        heading.
        """
        fields = list(super(SettingsForm, self).__iter__())
        group = lambda field: field.name.split("_", 1)[0].title()
        misc = _("Miscellaneous")
        groups = defaultdict(int)
        for field in fields:
            groups[group(field)] += 1
        for (i, field) in enumerate(fields):
            setattr(fields[i], "group", group(field))
            if groups[fields[i].group] == 1:
                fields[i].group = misc
        return iter(sorted(fields, key=lambda x: (x.group == misc, x.group)))

    def save(self):
        """
        Save each of the settings to the DB.
        """
        for (name, value) in self.cleaned_data.items():
            setting_name, language = name.rsplit("_", 1)
            setting, _ = Setting.objects.get_or_create(name=setting_name)
            with override(language):
                setting.value = value
            setting.save()

    def format_help(self, description):
        """
        Format the setting's description into HTML.
        """
        for bold in ("``", "*"):
            parts = []
            if description is None:
                description = ""
            for i, s in enumerate(description.split(bold)):
                parts.append(s if i % 2 == 0 else "<b>%s</b>" % s)
            description = "".join(parts)
        return mark_safe(urlize(description).replace("\n", "<br>"))
