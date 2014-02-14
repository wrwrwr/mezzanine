
from django.core.exceptions import ImproperlyConfigured
from django import forms
from django.forms import ValidationError
from django.forms.extras import SelectDateWidget
from django.forms.fields import FileField
from django.template.defaultfilters import filesizeformat
from django.utils.translation import ugettext_lazy as _

from mezzanine.conf import settings
from mezzanine.core.forms import SplitSelectDateTimeWidget
from mezzanine.utils.importing import import_dotted_path


class LimitedFileField(FileField):
    """
    Lets you limit maximum size and content type of uploaded files in a
    "user-friendly" way.

    Meant as an UI improvement rather than a security feature:
    * file size is properly limited using `FILE_UPLOAD_MAX_MEMORY_SIZE`
      or even better through server's configuration;
    * content type header cannot be trusted.
    """
    default_error_messages = {
        "max_size": _("Please ensure the file size is at most %(max)s "
                      "(currently %(size)s)."),
        "content_type": _("Please upload a file of an accepted type.")
    }

    def __init__(self, *args, **kwargs):
        self.max_size = kwargs.pop("max_size", settings.FORMS_UPLOAD_MAX_SIZE)
        self.content_types = kwargs.pop("content_types",
            settings.FORMS_UPLOAD_CONTENT_TYPES)
        super(LimitedFileField, self).__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        data = super(LimitedFileField, self).clean(data, initial)
        if data is None:
            return None
        elif not data and initial:
            return initial

        if self.max_size is not None:
            if data.size > self.max_size:
                error_values =  {"max": filesizeformat(self.max_size),
                                 "size": filesizeformat(data.size)}
                raise ValidationError(
                    self.error_messages["max_size"] % error_values)

        if self.content_types is not None:
            if data.content_type not in self.content_types:
                raise ValidationError(self.error_messages["content_type"])

        return data


# Constants for all available field types.
TEXT = 1
TEXTAREA = 2
EMAIL = 3
CHECKBOX = 4
CHECKBOX_MULTIPLE = 5
SELECT = 6
SELECT_MULTIPLE = 7
RADIO_MULTIPLE = 8
FILE = 9
DATE = 10
DATE_TIME = 11
HIDDEN = 12
NUMBER = 13
URL = 14
DOB = 15

# Names for all available field types.
NAMES = (
    (TEXT, _("Single line text")),
    (TEXTAREA, _("Multi line text")),
    (EMAIL, _("Email")),
    (NUMBER, _("Number")),
    (URL, _("URL")),
    (CHECKBOX, _("Check box")),
    (CHECKBOX_MULTIPLE, _("Check boxes")),
    (SELECT, _("Drop down")),
    (SELECT_MULTIPLE, _("Multi select")),
    (RADIO_MULTIPLE, _("Radio buttons")),
    (FILE, _("File upload")),
    (DATE, _("Date")),
    (DATE_TIME, _("Date/time")),
    (DOB, _("Date of birth")),
    (HIDDEN, _("Hidden")),
)

# Field classes for all available field types.
CLASSES = {
    TEXT: forms.CharField,
    TEXTAREA: forms.CharField,
    EMAIL: forms.EmailField,
    CHECKBOX: forms.BooleanField,
    CHECKBOX_MULTIPLE: forms.MultipleChoiceField,
    SELECT: forms.ChoiceField,
    SELECT_MULTIPLE: forms.MultipleChoiceField,
    RADIO_MULTIPLE: forms.ChoiceField,
    FILE: LimitedFileField,
    DATE: forms.DateField,
    DATE_TIME: forms.DateTimeField,
    DOB: forms.DateField,
    HIDDEN: forms.CharField,
    NUMBER: forms.FloatField,
    URL: forms.URLField,
}

# Widgets for field types where a specialised widget is required.
WIDGETS = {
    TEXTAREA: forms.Textarea,
    CHECKBOX_MULTIPLE: forms.CheckboxSelectMultiple,
    RADIO_MULTIPLE: forms.RadioSelect,
    DATE: SelectDateWidget,
    DATE_TIME: SplitSelectDateTimeWidget,
    DOB: SelectDateWidget,
    HIDDEN: forms.HiddenInput,
}

# Some helper groupings of field types.
CHOICES = (CHECKBOX, SELECT, RADIO_MULTIPLE)
DATES = (DATE, DATE_TIME, DOB)
MULTIPLE = (CHECKBOX_MULTIPLE, SELECT_MULTIPLE)

# HTML5 Widgets
if settings.FORMS_USE_HTML5:
    html5_field = lambda name, base: type("", (base,), {"input_type": name})
    WIDGETS.update({
        DATE: html5_field("date", forms.DateInput),
        DATE_TIME: html5_field("datetime", forms.DateTimeInput),
        DOB: html5_field("date", forms.DateInput),
        EMAIL: html5_field("email", forms.TextInput),
        NUMBER: html5_field("number", forms.TextInput),
        URL: html5_field("url", forms.TextInput),
    })


# Allow extra fields types to be defined via the FORMS_EXTRA_FIELDS
# setting, which should contain a sequence of three-item sequences,
# each containing the ID, dotted import path for the field class,
# and field name, for each custom field type.
for field_id, field_path, field_name in settings.FORMS_EXTRA_FIELDS:
    if field_id in CLASSES:
        err = "ID %s for field %s in FORMS_EXTRA_FIELDS already exists"
        raise ImproperlyConfigured(err % (field_id, field_name))
    CLASSES[field_id] = import_dotted_path(field_path)
    NAMES += ((field_id, _(field_name)),)
