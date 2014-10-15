from __future__ import unicode_literals
from future.builtins import open, range, str

from _ast import PyCF_ONLY_AST
from inspect import getmodule
import os
from shutil import copyfile, copytree
import sys
from warnings import warn

from django.apps import apps
from django.core.urlresolvers import clear_url_caches
from django.db import connection
from django.db.models.signals import (pre_migrate, post_migrate,
                                      pre_syncdb, post_syncdb)
from django.dispatch.dispatcher import _make_id
from django.template import Context, Template
from django.test import (TestCase as BaseTestCase,
                         modify_settings as base_modify_settings,
                         override_settings)
from django.test.runner import DiscoverRunner

from mezzanine.conf import import_defaults, settings
from mezzanine.pages.page_processors import import_page_processors
from mezzanine.utils.importing import path_for_import
from mezzanine.utils.models import get_user_model


User = get_user_model()


# Apps required by tests, assumed to always be installed.
# TODO: The idea here is to have some apps guaranteed in tests, but not
#       necessarily require users to install them, however. at the time of
#       writing you have to have the whole set in INSTALLED_APPS or some
#       tests will fail, mostly due to module-level defaults usage and
#       installation checks.
MANDATORY_APPS = (
    "mezzanine.boot",
    "mezzanine.conf",
    "mezzanine.core",
    "mezzanine.generic",
    # "mezzanine.blog",
    "mezzanine.forms",
    "mezzanine.pages",
    # "mezzanine.galleries",
    # "mezzanine.twitter",
    # "mezzanine.accounts",
    # "mezzanine.mobile",
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


class modify_settings(base_modify_settings):
    """
    Fixes two problems with ``modify_settings`` when used to extend installed
    apps outside of a test case. Hopefully, to be removed at some point.
    """
    def enable(self):
        # The app registry rebuilding creates new instances of AppConfigs,
        # but does not reregister signals for them (unless they're connected
        # in ``ready``). This causes pre/post_migrate signals not to be run
        # for the test databases (a signal emitted by the migration machinery
        # has a different sender id then the one stored by the dispatcher).
        # This usually shows up as a missing default Site (create_default_site
        # from contrib.sites is only connected for the original app instance).
        # TODO: Now, this is properly hackish :-) See Django ticket: #23641.
        old_app_ids = {_make_id(a): a.label for a in apps.get_app_configs()}
        super(modify_settings, self).enable()
        new_app_ids = {a.label: _make_id(a) for a in apps.get_app_configs()}
        for signal in (pre_migrate, post_migrate, pre_syncdb, post_syncdb):
            for index, ((receiver_id, sender_id), receiver) in enumerate(
                    signal.receivers):
                try:
                    new_sender_id = new_app_ids[old_app_ids[sender_id]]
                except KeyError:
                    # Receiver is not an app or the app has been uninstalled.
                    # TODO: Consider disconnecting uninstalled apps.
                    pass
                else:
                    signal.receivers[index] = ((receiver_id, new_sender_id),
                                               receiver)

        # Loading new models with foreign keys to those loaded previously
        # should invalidate related object caches.
        # TODO: Condsider also proposing a fix in Django, the problem can
        #       probably appear with typical modify_settings usage.
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


class TestRunner(DiscoverRunner):
    """
    Registers default settings and forces installation of mandatory
    and requested-to-be-tested apps not in ``INSTALLED_APPS``.

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
        installed_apps = [a.name for a in apps.get_app_configs() if
                          not a.name.startswith("django.contrib")]
        if "installed_apps" in test_labels:
            test_labels.remove("installed_apps")
            test_labels.extend(installed_apps)
        elif "installed_nonoptional_apps" in test_labels:
            test_labels.remove("installed_nonoptional_apps")
            test_labels.extend(a for a in installed_apps if
                               a not in settings.OPTIONAL_APPS)

        suite = super(TestRunner, self).build_suite(
            test_labels=test_labels, extra_tests=extra_tests, **kwargs)

        install = []
        for app in list(MANDATORY_APPS) + self.suite_apps(suite):
            if not apps.is_installed(app):
                warn("Package {} is to be tested or is mandatory for "
                     "testing, but is not in INSTALLED_APPS, it will be "
                     "loaded for the tests.".format(app))
                if app not in install:
                    install.append(app)
                    import_defaults(app)
        self.install = install

        # Rebuild the suite after loading defaults, some additional modules
        # now may be imported successfully.
        # TODO: In the long term strive to avoid using settings on the
        #       module level, and ensure that everything can be imported
        #       before any kind of autodiscovery is run.
        return super(TestRunner, self).build_suite(
            test_labels=test_labels, extra_tests=extra_tests, **kwargs)

    def setup_databases(self, **kwargs):
        with self.install_tested_and_mandatory():
            return super(TestRunner, self).setup_databases(**kwargs)

    def run_suite(self, suite, **kwargs):
        with self.install_tested_and_mandatory():
            if "mezzanine.urls" in sys.modules:
                # Mezzanine urls uses some "if installed" conditions,
                # and we've just changed installed apps.
                reload(sys.modules["mezzanine.urls"])
                clear_url_caches()
            for app_config in apps.get_app_configs():
                # Some newly installed apps can have page processors.
                import_page_processors(app_config.name)
            # Mezzanine tests need project urls, while Django in general
            # recommends tests not relying on user-defined urls.
            TestCase.urls = settings.ROOT_URLCONF
            with override_settings(ROOT_URLCONF="mezzanine.utils.test_urls"):
                return super(TestRunner, self).run_suite(suite, **kwargs)

    def teardown_databases(self, old_config, **kwargs):
        with self.install_tested_and_mandatory():
            return super(TestRunner, self).teardown_databases(old_config,
                                                              **kwargs)

    def suite_apps(self, suite):
        """
        Analyzes test cases in the ``suite`` trying to determine apps which
        the tests belong to.

        Only supports: ``app/tests.py`` and ``app/tests/*/module.py``, but
        works for modules that fail to import during discovery.
        """
        suite_apps = []
        for test in suite:
            if test.__class__.__name__ == "ModuleImportFailure":
                # Only partial test method name is preserved -- we'll have to
                # guess where the method could have been defined.
                # TODO: Remove this case once everything is guaranteed to be
                #       unconditionally importable.
                test_app = test._testMethodName
            else:
                # This is somewhat more resilent, but only works if for tests
                # that are importable without any app setup.
                test_method = getattr(test, test._testMethodName)
                test_app = getmodule(test_method).__package__
            try:
                test_app = test_app[:test_app.index(".tests")]
            except ValueError:
                pass
            suite_apps.append(test_app)
        return suite_apps

    def install_tested_and_mandatory(self):
        return modify_settings(INSTALLED_APPS={"append": self.install})


class TestCase(BaseTestCase):
    """
    This is the base test case providing common features for all tests
    across the different apps in Mezzanine.

    Among other things it sets the ``ROOT_URLCONF`` to the project
    urls (as defined in your settings), whereas an empty urls file is
    used for test cases not deriving from this one to support testing
    ``django.contrib`` apps.
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
