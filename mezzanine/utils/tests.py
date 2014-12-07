from __future__ import unicode_literals
from future.builtins import open, range, str

from _ast import PyCF_ONLY_AST
import os
from shutil import copyfile, copytree

from django import VERSION
from django.core.management import call_command
from django.db import connection
from django.template import Context, Template
from django.test import TestCase as BaseTestCase
from django.test.client import RequestFactory
from django.test.simple import DjangoTestSuiteRunner
from django.utils.unittest import skipUnless

from mezzanine.conf import settings
from mezzanine.utils.importing import path_for_import
from mezzanine.utils.models import get_user_model

if "south" in settings.INSTALLED_APPS:
    from south.signals import post_migrate
else:
    if VERSION >= (1, 7):
        from django.db.models.signals import post_migrate
    else:
        from django.db.models.signals import post_syncdb as post_migrate


User = get_user_model()


# Ignore these warnings in pyflakes - if added to, please comment why.
IGNORE_ERRORS = (

    # local_settings import.
    "'from local_settings import *' used",

    # Used to version subpackages.
    "'__version__' imported but unused",

    # No caching fallback
    "redefinition of function 'nevercache'",

    # Dummy fallback in templates for django-compressor
    "redefinition of function 'compress'",

    # Fabic config fallback
    "redefinition of unused 'conf'",

    # Fixing these would make the code ugiler IMO.
    "continuation line",
    "closing bracket does not match",

    # Jython compatiblity
    "redefinition of unused 'Image",

    # Django 1.5 custom user compatibility
    "redefinition of unused 'get_user_model",

    # Django 1.5 deprecated methods compatibility.
    "'get_permission_codename' imported but unused",

    # Actually a Python template file.
    "live_settings.py",

)


class TestRunner(DjangoTestSuiteRunner):
    def setup_databases(self, **kwargs):
        """
        Creates and updates translation fields as part of preparing the
        test database.
        """
        if settings.USE_MODELTRANSLATION:
            def create_translation_fields(sender, **kwargs):
                kwargs.setdefault("verbosity", 0)
                kwargs.setdefault("interactive", False)
                call_command("sync_translation_fields", **kwargs)
                call_command("update_translation_fields", **kwargs)
            # Note: the signal is purposefully not disconnected, to support
            # migrations within test cases.
            post_migrate.connect(create_translation_fields)
        return super(TestRunner, self).setup_databases(**kwargs)


class TestCase(BaseTestCase):
    """
    This is the base test case providing common features for all tests
    across the different apps in Mezzanine.
    """

    def setUp(self):
        """
        Creates an admin user, sets up the debug cursor, so that we can
        track the number of queries used in various places, and creates
        a request factory for views testing.
        """
        self._username = "test"
        self._password = "test"
        self._emailaddress = "example@example.com"
        args = (self._username, self._emailaddress, self._password)
        self._user = User.objects.create_superuser(*args)
        self._debug_cursor = connection.use_debug_cursor
        self._request_factory = RequestFactory()
        connection.use_debug_cursor = True

    def tearDown(self):
        """
        Clean up the admin user created and debug cursor.
        """
        self._user.delete()
        connection.use_debug_cursor = self._debug_cursor

    def queries_used_for_template(self, template, **context):
        """
        Return the number of queries used when rendering a template
        string.
        """
        connection.queries = []
        t = Template(template)
        t.render(Context(context))
        return len(connection.queries)

    def create_recursive_objects(self, model, parent_field, **kwargs):
        """
        Create multiple levels of recursive objects.
        """
        per_level = list(range(3))
        for _ in per_level:
            kwargs[parent_field] = None
            level1 = model.objects.create(**kwargs)
            for _ in per_level:
                kwargs[parent_field] = level1
                level2 = model.objects.create(**kwargs)
                for _ in per_level:
                    kwargs[parent_field] = level2
                    model.objects.create(**kwargs)


@skipUnless(settings.USE_MODELTRANSLATION,
            "modeltranslation must be enabled before Django setup")
class ContentTranslationTestCase(TestCase):
    """
    Base case for content translation tests. Any case deriving from this
    class will be skipped if content translation is disabled.

    Provides some commonly needed variables:

        languages
            list of languages used by content translation;

        fallbacks
            dict mapping language code to codes of languages that will be
            used if a translation is missing (in the order given);

        fallback_pair
            2-tuple with one language that will first fall back to the other
            one (``None`` if fallbacks are disabled or none are defined);

        no_fallback_pair
            2-tuple with the first language that will certainly not
            fall back to the second one.
    """
    @classmethod
    def setUpClass(cls):
        # At this point we know that USE_MODELTRANSLATION is true, so we may
        # try to import its modules.
        from modeltranslation import settings as mt_settings
        cls.mt_settings = mt_settings
        # Content translation languages (may not be the same as LANGUAGES).
        # AVAILABLE_LANGUAGES is a generator, so we need to tuple it.
        cls.languages = tuple(mt_settings.AVAILABLE_LANGUAGES)

        # Some tests need falling or non-falling back languages, to prepare
        # for various cases lets resolve fallbacks for all languages.
        from modeltranslation.utils import resolution_order
        cls.fallbacks = dict((l, resolution_order(l)) for l in cls.languages)
        # First language in the pair will first fall back to the second one.
        cls.fallback_pair = None
        for language, language_fallbacks in cls.fallbacks.items():
            if len(language_fallbacks) > 1:
                cls.fallback_pair = (language, language_fallbacks[1])
                break
        # The first language will certainly not fall back to the second one.
        cls.no_fallback_pair = None
        for language, language_fallbacks in cls.fallbacks.items():
            non_fallbacks = set(cls.languages) - set(language_fallbacks)
            if non_fallbacks:
                cls.no_fallback_pair = (language, next(iter(non_fallbacks)))
                break


def copy_test_to_media(module, name):
    """
    Copies a file from Mezzanine's test data path to MEDIA_ROOT.
    Used in tests and demo fixtures.
    """
    mezzanine_path = path_for_import(module)
    test_path = os.path.join(mezzanine_path, "static", "test", name)
    to_path = os.path.join(settings.MEDIA_ROOT, name)
    to_dir = os.path.dirname(to_path)
    if not os.path.exists(to_dir):
        os.makedirs(to_dir)
    if os.path.isdir(test_path):
        copy = copytree
    else:
        copy = copyfile
    try:
        copy(test_path, to_path)
    except OSError:
        pass


def _run_checker_for_package(checker, package_name, extra_ignore=None):
    """
    Runs the checker function across every Python module in the
    given package.
    """
    ignore_strings = IGNORE_ERRORS
    if extra_ignore:
        ignore_strings += extra_ignore
    package_path = path_for_import(package_name)
    for (root, dirs, files) in os.walk(str(package_path)):
        for f in files:
            if (f == "local_settings.py" or not f.endswith(".py") or
                    root.split(os.sep)[-1] in ["migrations", "south"]):
                # Ignore
                continue
            for warning in checker(os.path.join(root, f)):
                for ignore in ignore_strings:
                    if ignore in warning:
                        break
                else:
                    yield warning.replace(package_path, package_name, 1)


def run_pyflakes_for_package(package_name, extra_ignore=None):
    """
    If pyflakes is installed, run it across the given package name
    returning any warnings found.
    """
    from pyflakes.checker import Checker

    def pyflakes_checker(path):
        with open(path, "U") as source_file:
            source = source_file.read()
        try:
            tree = compile(source, path, "exec", PyCF_ONLY_AST)
        except (SyntaxError, IndentationError) as value:
            info = (path, value.lineno, value.args[0])
            yield "Invalid syntax in %s:%d: %s" % info
        else:
            result = Checker(tree, path)
            for warning in result.messages:
                yield str(warning)

    args = (pyflakes_checker, package_name, extra_ignore)
    return _run_checker_for_package(*args)


def run_pep8_for_package(package_name, extra_ignore=None):
    """
    If pep8 is installed, run it across the given package name
    returning any warnings or errors found.
    """
    import pep8

    class Checker(pep8.Checker):
        """
        Subclass pep8's Checker to hook into error reporting.
        """
        def __init__(self, *args, **kwargs):
            super(Checker, self).__init__(*args, **kwargs)
            self.report_error = self._report_error

        def _report_error(self, line_number, offset, text, check):
            """
            Store pairs of line numbers and errors.
            """
            self.errors.append((line_number, text.split(" ", 1)[1]))

        def check_all(self, *args, **kwargs):
            """
            Assign the errors attribute and return it after running.
            """
            self.errors = []
            super(Checker, self).check_all(*args, **kwargs)
            return self.errors

    def pep8_checker(path):
        for line_number, text in Checker(path).check_all():
            yield "%s:%s: %s" % (path, line_number, text)

    args = (pep8_checker, package_name, extra_ignore)
    return _run_checker_for_package(*args)
