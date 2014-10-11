from __future__ import unicode_literals
from future.builtins import open, range, str

from _ast import PyCF_ONLY_AST
from fnmatch import fnmatch
from importlib import import_module
import os
from pkgutil import walk_packages
from shutil import copyfile, copytree
from warnings import warn

from django.apps import apps
from django.db import connection
from django.db.models.signals import (pre_migrate, post_migrate,
                                      pre_syncdb, post_syncdb)
from django.dispatch.dispatcher import _make_id
from django.template import Context, Template
from django.test import TestCase as BaseTestCase
from django.test.runner import DiscoverRunner

from mezzanine.conf import import_defaults, settings
from mezzanine.utils.importing import path_for_import
from mezzanine.utils.models import get_user_model


User = get_user_model()


# Apps required by tests, assumed to always be installed.
MANDATORY_APPS = (
    "mezzanine.boot",
    "mezzanine.conf",
    "mezzanine.core",
    "mezzanine.generic",
    "mezzanine.pages",
)


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

    # Actually a Python template file.
    "live_settings.py",

)


class TestRunner(DiscoverRunner):
    """
    Registers default settings and forces installation of non-installed apps
    requested to be tested and mandatory apps not in ``INSTALLED_APPS``.

    Also provides two additional test targets:
    * ``installed_apps``: runs tests for apps in ``INSTALLED_APPS``,
      except ``django.contrib`` modules;
    * ``installed_nonoptional_apps``: also excludes apps from the
      ``OPTIONAL_APPS`` list.

    Some examples:
    * ``./manage.py test``: only your project tests;
    * ``./manage.py test mezzanine``: the whole Mezzanine suite,
      including apps you have commented out in your settings;
    * ``./manage.py test mezzanine.core``: tests for a single app;
    * ``./manage.py test mezzanine.core.tests.CoreTests.test_syntax``:
      a single test.
    """

    def build_suite(self, test_labels=None, extra_tests=None, **kwargs):
        test_labels = list(test_labels)
        if "installed_apps" in test_labels:
            test_labels.remove("installed_apps")
            test_labels.extend(a for a in settings.INSTALLED_APPS if
                                not a.startswith("django.contrib"))
        elif "installed_nonoptional_apps" in test_labels:
            test_labels.remove("installed_nonoptional_apps")
            test_labels.extend(a for a in settings.INSTALLED_APPS if
                                a not in settings.OPTIONAL_APPS and
                                not a.startswith("django.contrib"))

        # Register default settings and force installation for missing
        # mandatory and tested non-installed apps.
        packages = self.packages_for_labels(test_labels) + list(MANDATORY_APPS)
        settings.INSTALLED_APPS = list(settings.INSTALLED_APPS)
        for package in packages:
            if package not in settings.INSTALLED_APPS:
                warn("Package {} is to be tested or is mandatory for testing, "
                     "but is not in INSTALLED_APPS, it will be loaded for the "
                     "tests.".format(package))
                import_defaults(package)
                settings.INSTALLED_APPS += (package,)

        # The app registry rebuilding creates new instances of AppConfigs,
        # but does not reregister signals for them (unless they're connected
        # in ``ready``). This causes pre/post_migrate signals not to be run
        # for the test databases (a signal emitted by the migration machinery
        # has a different sender id then the one stored by the dispatcher).
        # This usually shows up as a missing default Site (create_default_site
        # from contrib.sites is only connected for the original app instance).
        # TODO: Now, this is properly hackish :-)
        old_app_ids = {_make_id(a): a.label for a in apps.get_app_configs()}
        apps.set_installed_apps(settings.INSTALLED_APPS)
        new_app_ids = {a.label: _make_id(a) for a in apps.get_app_configs()}
        for signal in (pre_migrate, post_migrate, pre_syncdb, post_syncdb):
            for index, ((receiver_id, sender_id), receiver) in enumerate(
                    signal.receivers):
                if sender_id in old_app_ids:
                    # Note: we're only adding apps.
                    new_sender_id = new_app_ids[old_app_ids[sender_id]]
                    signal.receivers[index] = ((receiver_id, new_sender_id),
                                               receiver)

        # Loading new models with foreign keys to those loaded previously
        # should invalidate related object caches.
        # TODO: Any cleaner solution to "missing" related fields?
        for model in apps.get_models():
            opts = model._meta
            related_caches = ("_related_objects_cache",
                              "_related_objects_proxy_cache",
                              "_related_many_to_many_cache",)
            for cache in related_caches:
                try:
                    delattr(opts, cache)
                except AttributeError:
                    pass

        return super(TestRunner, self).build_suite(
            test_labels=test_labels, extra_tests=extra_tests, **kwargs)

    def packages_for_labels(self, test_labels):
        """
        Finds what packages are to be tested based on test labels.

        Packages to be tested are understood as packages specified by a label
        or any of their subpackages, that contain some tests (modules matching
        ``self.pattern``).

        TODO: Consider subclassing TestLoader, getting the actual tests list
              (while avoiding to trigger import exceptions) would be more
              accurate.
        """

        packages = []
        for label in test_labels:
            if os.path.exists(os.path.abspath(label)):
                # Label is a file system path, we could support a case with
                # the path pointing to a Python package, but is it worth it?
                warn("Specifying tests by directory paths is not supported, "
                     "requested tests for non-installed apps may fail, "
                     "please use a dotted package or module names.")
                continue
            # Label is a dotted package, module, test case or a method name.
            # Find the most-specific package in the label.
            label_package = None
            parts = label.split(".")
            while parts:
                try:
                    module = import_module(".".join(parts))
                except:
                    # No such module or there is a module, but trying to import
                    # it raises an exception, possibly due to unloaded defaults
                    # -- we'll try loading defaults from its package.
                    del parts[-1]
                else:
                    if hasattr(module, "__path__"):
                        # Let's say if it has a path attribute it's a package.
                        label_package = module
                    else:
                        # Package import should succeed considering its module
                        # got imported, anyway we don't know what to do if it
                        # fails.
                        label_package = import_module(module.__package__)
                    break
            if label_package is not None:
                # For labels like "mezzanine" we need to process subpackages.
                for loader, name, _ in walk_packages(
                        label_package.__path__, label_package.__name__ + "."):
                    module_filename = os.path.basename(
                        loader.find_module(name).filename)
                    if fnmatch(module_filename, self.pattern):
                        package = ".".join(name.split(".")[:-1])
                        packages.append(package)
        return packages


class TestCase(BaseTestCase):
    """
    This is the base test case providing common features for all tests
    across the different apps in Mezzanine.
    """

    def setUp(self):
        """
        Creates an admin user and sets up the debug cursor, so that
        we can track the number of queries used in various places.
        """
        self._username = "test"
        self._password = "test"
        self._emailaddress = "example@example.com"
        args = (self._username, self._emailaddress, self._password)
        self._user = User.objects.create_superuser(*args)
        self._debug_cursor = connection.use_debug_cursor
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
