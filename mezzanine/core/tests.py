from __future__ import unicode_literals

import inspect
import re

try:
    # Python 3
    from urllib.parse import urlencode
except ImportError:
    # Python 2
    from urllib import urlencode

from django import VERSION
from django.contrib.admin import AdminSite, ModelAdmin, site as admin_site
from django.contrib.admin.options import InlineModelAdmin
from django.contrib.sites.models import Site
from django.core import mail
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.db import models
from django.forms import Textarea
from django.forms.models import modelform_factory
from django.templatetags.static import static
from django.test.utils import override_settings
from django.utils.html import strip_tags
from django.utils.translation import get_language, override
from django.utils.unittest import skipIf, skipUnless

from mezzanine.conf import settings
from mezzanine.core.admin import (BaseDynamicInlineAdmin,
                                  TranslationModelAdmin,
                                  TranslationInlineModelAdmin)
from mezzanine.core.fields import RichTextField
from mezzanine.core.managers import DisplayableManager
from mezzanine.core.models import (CONTENT_STATUS_DRAFT,
                                   CONTENT_STATUS_PUBLISHED, Slugged)
from mezzanine.forms.admin import FieldAdmin
from mezzanine.forms.models import Form
from mezzanine.pages.models import RichTextPage
from mezzanine.utils.importing import import_dotted_path
from mezzanine.utils.sites import current_site_id
from mezzanine.utils.tests import (ContentTranslationTestCase, TestCase,
                                   run_pep8_for_package,
                                   run_pyflakes_for_package)
from mezzanine.utils.translation import for_all_languages, disable_fallbacks
from mezzanine.utils.html import TagCloser


class CoreTests(TestCase):

    def test_tagcloser(self):
        """
        Test tags are closed, and tags that shouldn't be closed aren't.
        """
        self.assertEqual(TagCloser("<p>Unclosed paragraph").html,
                         "<p>Unclosed paragraph</p>")

        self.assertEqual(TagCloser("Line break<br>").html,
                         "Line break<br>")

    @skipUnless("mezzanine.mobile" in settings.INSTALLED_APPS and
                "mezzanine.pages" in settings.INSTALLED_APPS,
                "mobile and pages apps required")
    def test_device_specific_template(self):
        """
        Test that an alternate template is rendered when a mobile
        device is used.
        """
        ua = settings.DEVICE_USER_AGENTS[0][1][0]
        kwargs = {"slug": "device-test"}
        url = reverse("page", kwargs=kwargs)
        kwargs["status"] = CONTENT_STATUS_PUBLISHED
        RichTextPage.objects.get_or_create(**kwargs)
        default = self.client.get(url)
        mobile = self.client.get(url, HTTP_USER_AGENT=ua)
        self.assertNotEqual(default.template_name[0], mobile.template_name[0])

    def test_syntax(self):
        """
        Run pyflakes/pep8 across the code base to check for potential errors.
        """
        warnings = []
        warnings.extend(run_pyflakes_for_package("mezzanine"))
        warnings.extend(run_pep8_for_package("mezzanine"))
        if warnings:
            self.fail("Syntax warnings!\n\n%s" % "\n".join(warnings))

    def test_utils(self):
        """
        Miscellanous tests for the ``mezzanine.utils`` package.
        """
        self.assertRaises(ImportError, import_dotted_path, "mezzanine")
        self.assertRaises(ImportError, import_dotted_path, "mezzanine.NO")
        self.assertRaises(ImportError, import_dotted_path, "mezzanine.core.NO")
        try:
            import_dotted_path("mezzanine.core")
        except ImportError:
            self.fail("mezzanine.utils.imports.import_dotted_path"
                      "could not import \"mezzanine.core\"")

    @skipUnless("mezzanine.pages" in settings.INSTALLED_APPS,
                "pages app required")
    def test_description(self):
        """
        Test generated description is text version of the first line
        of content.
        """
        description = "<p>How now brown cow</p>"
        page = RichTextPage.objects.create(title="Draft",
                                           content=description * 3)
        self.assertEqual(page.description, strip_tags(description))

    @skipUnless("mezzanine.pages" in settings.INSTALLED_APPS,
                "pages app required")
    def test_draft(self):
        """
        Test a draft object as only being viewable by a staff member.
        """
        self.client.logout()
        draft = RichTextPage.objects.create(title="Draft",
                                            status=CONTENT_STATUS_DRAFT)
        response = self.client.get(draft.get_absolute_url(), follow=True)
        self.assertEqual(response.status_code, 404)
        self.client.login(username=self._username, password=self._password)
        response = self.client.get(draft.get_absolute_url(), follow=True)
        self.assertEqual(response.status_code, 200)

    def test_searchable_manager_search_fields(self):
        """
        Test that SearchableManager can get appropriate params.
        """
        manager = DisplayableManager()
        self.assertFalse(manager._search_fields)
        manager = DisplayableManager(search_fields={'foo': 10})
        self.assertTrue(manager._search_fields)

    @skipUnless("mezzanine.pages" in settings.INSTALLED_APPS,
                "pages app required")
    def test_search(self):
        """
        Objects with status "Draft" should not be within search results.
        """
        RichTextPage.objects.all().delete()
        published = {"status": CONTENT_STATUS_PUBLISHED}
        first = RichTextPage.objects.create(title="test page",
                                           status=CONTENT_STATUS_DRAFT).id
        second = RichTextPage.objects.create(title="test another test page",
                                            **published).id
        # Draft shouldn't be a result.
        results = RichTextPage.objects.search("test")
        self.assertEqual(len(results), 1)
        RichTextPage.objects.filter(id=first).update(**published)
        results = RichTextPage.objects.search("test")
        self.assertEqual(len(results), 2)
        # Either word.
        results = RichTextPage.objects.search("another test")
        self.assertEqual(len(results), 2)
        # Must include first word.
        results = RichTextPage.objects.search("+another test")
        self.assertEqual(len(results), 1)
        # Mustn't include first word.
        results = RichTextPage.objects.search("-another test")
        self.assertEqual(len(results), 1)
        if results:
            self.assertEqual(results[0].id, first)
        # Exact phrase.
        results = RichTextPage.objects.search('"another test"')
        self.assertEqual(len(results), 1)
        if results:
            self.assertEqual(results[0].id, second)
        # Test ordering.
        results = RichTextPage.objects.search("test")
        self.assertEqual(len(results), 2)
        if results:
            self.assertEqual(results[0].id, second)
        # Test the actual search view.
        response = self.client.get(reverse("search") + "?q=test")
        self.assertEqual(response.status_code, 200)

    def _create_page(self, title, status):
        return RichTextPage.objects.create(title=title, status=status)

    def _test_site_pages(self, title, status, count):
        # test _default_manager
        pages = RichTextPage._default_manager.all()
        self.assertEqual(pages.count(), count)
        self.assertTrue(title in [page.title for page in pages])

        # test objects manager
        pages = RichTextPage.objects.all()
        self.assertEqual(pages.count(), count)
        self.assertTrue(title in [page.title for page in pages])

        # test response status code
        code = 200 if status == CONTENT_STATUS_PUBLISHED else 404
        pages = RichTextPage.objects.filter(status=status)
        response = self.client.get(pages[0].get_absolute_url(), follow=True)
        self.assertEqual(response.status_code, code)

    @skipUnless("mezzanine.pages" in settings.INSTALLED_APPS,
                "pages app required")
    def test_multisite(self):
        from django.conf import settings

        # setup
        try:
            old_site_id = settings.SITE_ID
        except:
            old_site_id = None

        site1 = Site.objects.create(domain="site1.com")
        site2 = Site.objects.create(domain="site2.com")

        # create pages under site1, which should be only accessible
        # when SITE_ID is site1
        settings.SITE_ID = site1.pk
        site1_page = self._create_page("Site1", CONTENT_STATUS_PUBLISHED)
        self._test_site_pages("Site1", CONTENT_STATUS_PUBLISHED, count=1)

        # create pages under site2, which should only be accessible
        # when SITE_ID is site2
        settings.SITE_ID = site2.pk
        self._create_page("Site2", CONTENT_STATUS_PUBLISHED)
        self._test_site_pages("Site2", CONTENT_STATUS_PUBLISHED, count=1)

        # original page should 404
        response = self.client.get(site1_page.get_absolute_url(), follow=True)
        self.assertEqual(response.status_code, 404)

        # change back to site1, and only the site1 pages should be retrieved
        settings.SITE_ID = site1.pk
        self._test_site_pages("Site1", CONTENT_STATUS_PUBLISHED, count=1)

        # insert a new record, see the count change
        self._create_page("Site1 Draft", CONTENT_STATUS_DRAFT)
        self._test_site_pages("Site1 Draft", CONTENT_STATUS_DRAFT, count=2)
        self._test_site_pages("Site1 Draft", CONTENT_STATUS_PUBLISHED, count=2)

        # change back to site2, and only the site2 pages should be retrieved
        settings.SITE_ID = site2.pk
        self._test_site_pages("Site2", CONTENT_STATUS_PUBLISHED, count=1)

        # insert a new record, see the count change
        self._create_page("Site2 Draft", CONTENT_STATUS_DRAFT)
        self._test_site_pages("Site2 Draft", CONTENT_STATUS_DRAFT, count=2)
        self._test_site_pages("Site2 Draft", CONTENT_STATUS_PUBLISHED, count=2)

        # tear down
        if old_site_id:
            settings.SITE_ID = old_site_id
        else:
            del settings.SITE_ID

        site1.delete()
        site2.delete()

    def _static_proxy(self, querystring):
        self.client.login(username=self._username, password=self._password)
        proxy_url = '%s?%s' % (reverse('static_proxy'), querystring)
        response = self.client.get(proxy_url)
        self.assertEqual(response.status_code, 200)

    @override_settings(STATIC_URL='/static/')
    def test_static_proxy(self):
        querystring = urlencode([('u', static("test/image.jpg"))])
        self._static_proxy(querystring)

    @override_settings(STATIC_URL='http://testserver/static/')
    def test_static_proxy_with_host(self):
        querystring = urlencode(
            [('u', static("test/image.jpg"))])
        self._static_proxy(querystring)

    @override_settings(STATIC_URL='http://testserver:8000/static/')
    def test_static_proxy_with_static_url_with_full_host(self):
        from django.templatetags.static import static
        querystring = urlencode([('u', static("test/image.jpg"))])
        self._static_proxy(querystring)

    def _get_csrftoken(self, response):
        csrf = re.findall(
            b'\<input type\=\'hidden\' name\=\'csrfmiddlewaretoken\' '
            b'value\=\'([^"\']+)\' \/\>',
            response.content
        )
        self.assertEqual(len(csrf), 1, 'No csrfmiddlewaretoken found!')
        return csrf[0]

    def _get_formurl(self, response):
        action = re.findall(
            b'\<form action\=\"([^\"]*)\" method\=\"post\"\>',
            response.content
        )
        self.assertEqual(len(action), 1, 'No form with action found!')
        if action[0] == b'':
            action = response.request['PATH_INFO']
        return action

    @skipUnless('mezzanine.pages' in settings.INSTALLED_APPS,
                'pages app required')
    @override_settings(LANGUAGE_CODE="en")
    def test_password_reset(self):
        """
        Test sending of password-reset mails and evaluation of the links.
        """
        self.client.logout()
        del mail.outbox[:]

        # Go to admin-login, search for reset-link
        response = self.client.get('/admin/', follow=True)
        self.assertContains(response, u'Forgot password?')
        url = re.findall(
            b'\<a href\=["\']([^\'"]+)["\']\>Forgot password\?\<\/a\>',
            response.content
        )
        self.assertEqual(len(url), 1)
        url = url[0]

        # Go to reset-page, submit form
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        csrf = self._get_csrftoken(response)
        url = self._get_formurl(response)

        response = self.client.post(url, {
            'csrfmiddlewaretoken': csrf,
            'email': self._emailaddress
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

        # Get reset-link, submit form
        url = re.findall(
            r'http://example.com(/reset/[^/]+/[^/]+/)',
            mail.outbox[0].body
        )[0]
        response = self.client.get(url)
        csrf = self._get_csrftoken(response)
        url = self._get_formurl(response)
        if VERSION < (1, 6):
            return
        response = self.client.post(url, {
            'csrfmiddlewaretoken': csrf,
            'new_password1': 'newdefault',
            'new_password2': 'newdefault'
        }, follow=True)
        self.assertEqual(response.status_code, 200)

    def test_richtext_widget(self):
        """
        Test that the RichTextField gets its widget type correctly from
        settings, and is able to be overridden in a form's Meta.
        """

        class RichTextModel(models.Model):
            text_default = RichTextField()
            text_overridden = RichTextField()

        form_class = modelform_factory(
            RichTextModel,
            fields=('text_default', 'text_overridden'),
            widgets={'text_overridden': Textarea})
        form = form_class()

        richtext_widget = import_dotted_path(settings.RICHTEXT_WIDGET_CLASS)

        self.assertIsInstance(form.fields['text_default'].widget,
                              richtext_widget)
        self.assertIsInstance(form.fields['text_overridden'].widget,
                              Textarea)

    def test_admin_sites_dropdown(self):
        """
        Ensures the site selection dropdown appears in the admin.
        """
        self.client.login(username=self._username, password=self._password)
        response = self.client.get('/admin/', follow=True)
        set_site_url = reverse("set_site")
        # Set site URL shouldn't appear without multiple sites.
        self.assertNotContains(response, set_site_url)
        site1 = Site.objects.create(domain="test-site-dropdown1.com",
                                    name="test-site-dropdown1.com")
        site2 = Site.objects.create(domain="test-site-dropdown2.com",
                                    name="test-site-dropdown2.com")
        response = self.client.get('/admin/', follow=True)
        self.assertContains(response, set_site_url)
        self.assertContains(response, site1.name)
        self.assertContains(response, site2.name)
        site1.delete()
        site2.delete()

    def test_dynamic_inline_admins(self):
        """
        Verifies that ``BaseDynamicInlineAdmin`` properly adds the ``_order``
        field for admins of ``Orderable`` subclasses.
        """
        request = self._request_factory.get('/admin/')
        request.user = self._user
        field_admin = FieldAdmin(Form, AdminSite())
        fieldsets = field_admin.get_fieldsets(request)
        self.assertEqual(fieldsets[0][1]['fields'][-1], '_order')
        if VERSION >= (1, 7):
            fields = field_admin.get_fields(request)
            self.assertEqual(fields[-1], '_order')

    def test_dynamic_inline_admins_fields_tuple(self):
        """
        Checks if moving the ``_order`` field works with immutable sequences.
        """
        class MyModelInline(BaseDynamicInlineAdmin, InlineModelAdmin):
            # Any model would work since we're only instantiating the class and
            # not actually using it.
            model = RichTextPage
            fields = ('a', '_order', 'b')

        request = self._request_factory.get('/admin/')
        inline = MyModelInline(None, None)
        fields = inline.get_fieldsets(request)[0][1]['fields']
        self.assertSequenceEqual(fields, ('a', 'b', '_order'))

    def test_dynamic_inline_admins_fields_without_order(self):
        """
        Checks that ``_order`` field will be added if ``fields`` are listed
        without it.
        """
        class MyModelInline(BaseDynamicInlineAdmin, InlineModelAdmin):
            model = RichTextPage
            fields = ('a', 'b')

        request = self._request_factory.get('/admin/')
        inline = MyModelInline(None, None)
        fields = inline.get_fieldsets(request)[0][1]['fields']
        self.assertSequenceEqual(fields, ('a', 'b', '_order'))

    def test_dynamic_inline_admins_fieldsets(self):
        """
        Tests if ``_order`` is moved to the end of the last fieldsets fields.
        """
        class MyModelInline(BaseDynamicInlineAdmin, InlineModelAdmin):
            model = RichTextPage
            fieldsets = (("Fieldset 1", {'fields': ('a',)}),
                         ("Fieldset 2", {'fields': ('_order', 'b')}),
                         ("Fieldset 3", {'fields': ('c')}))

        request = self._request_factory.get('/admin/')
        inline = MyModelInline(None, None)
        fieldsets = inline.get_fieldsets(request)
        self.assertEqual(fieldsets[-1][1]["fields"][-1], '_order')
        self.assertNotIn('_order', fieldsets[1][1]["fields"])


@skipUnless("mezzanine.pages" in settings.INSTALLED_APPS,
            "pages app required")
class SiteRelatedTestCase(TestCase):

    def test_update_site(self):
        from django.conf import settings

        # setup
        try:
            old_site_id = settings.SITE_ID
        except:
            old_site_id = None

        site1 = Site.objects.create(domain="site1.com")
        site2 = Site.objects.create(domain="site2.com")

        # default behaviour, page gets assigned current site
        settings.SITE_ID = site2.pk
        self.assertEqual(settings.SITE_ID, current_site_id())
        page = RichTextPage()
        page.save()
        self.assertEqual(page.site_id, site2.pk)

        # Subsequent saves do not update site to current site
        page.site = site1
        page.save()
        self.assertEqual(page.site_id, site1.pk)

        # resave w/ update_site=True, page gets assigned current site
        settings.SITE_ID = site1.pk
        page.site = site2
        page.save(update_site=True)
        self.assertEqual(page.site_id, site1.pk)

        # resave w/ update_site=False, page does not update site
        settings.SITE_ID = site2.pk
        page.save(update_site=False)
        self.assertEqual(page.site_id, site1.pk)

        # When update_site=True, new page gets assigned current site
        settings.SITE_ID = site2.pk
        page = RichTextPage()
        page.site = site1
        page.save(update_site=True)
        self.assertEqual(page.site_id, site2.pk)

        # When update_site=False, new page keeps current site
        settings.SITE_ID = site2.pk
        page = RichTextPage()
        page.site = site1
        page.save(update_site=False)
        self.assertEqual(page.site_id, site1.pk)

        # When site explicitly assigned, new page keeps assigned site
        settings.SITE_ID = site2.pk
        page = RichTextPage()
        page.site = site1
        page.save()
        self.assertEqual(page.site_id, site1.pk)

        # tear down
        if old_site_id:
            settings.SITE_ID = old_site_id
        else:
            del settings.SITE_ID

        site1.delete()
        site2.delete()


@skipIf(settings.USE_MODELTRANSLATION,
        "modeltranslation must be disabled before Django setup")
class NoContentTranslationTests(TestCase):
    """
    Disabled content translation should be equivalent to no content
    translation.
    """
    def test_switch(self):
        """
        If ``USE_MODELTRANSLATION`` is false, modeltranslation should not be
        loaded.
        """
        self.assertNotIn('modeltranslation', settings.INSTALLED_APPS)
        try:
            from modeltranslation.translator import translator
        except ImportError:
            pass
        else:
            self.assertEqual(len(translator.get_registered_models()), 0)

    def test_for_all_languages(self):
        """
        The provided function should be executed exactly once.
        """
        nl = {'calls': 0}  # Python 3+: nonlocal

        def function():
            nl['calls'] += 1
        for_all_languages(function)
        self.assertEqual(nl['calls'], 1)

    def test_for_all_languages_exception(self):
        """
        The helper shouldn't hide exceptions.
        """
        def function():
            raise RuntimeError()

        with self.assertRaises(RuntimeError):
            for_all_languages(function)

    def test_disable_fallbacks(self):
        """
        Without content translation, disabling fallbacks should have no
        effect.
        """
        with disable_fallbacks():
            pass

    def test_disable_fallbacks_exception(self):
        """
        The helper shouldn't hide exceptions.
        """
        with self.assertRaises(RuntimeError):
            with disable_fallbacks():
                raise RuntimeError

    @skipUnless('mezzanine.pages' in settings.INSTALLED_APPS,
                "needs the Page model to be migrated and registered")
    def test_save_performance(self):
        """
        Reference for the test in ``ContentTranslationTests``, if you change
        the count in this one, please also update it there.
        """
        from mezzanine.pages.models import Page
        with self.assertNumQueries(6):
            # Note: Should be 3 at most -- site query, page query and insert.
            page = Page(title="a")
            page.save()

    def test_admins_bases(self):
        """
        Without content translation, deriving from ``TranslationModelAdmin``
        should be as good as deriving from ``ModelAdmin``.
        """
        class Admin1(TranslationModelAdmin):
            pass

        class Admin2(ModelAdmin):
            pass

        self.assertEqual(inspect.getmro(Admin1)[1:],
                         inspect.getmro(Admin2)[1:])

    def test_inline_admins_bases(self):
        """
        Deriving from ``TranslationInlineModelAdmin`` should be equivalent to
        deriving from ``InlineModelAdmin``.
        """
        class InlineAdmin1(TranslationInlineModelAdmin):
            pass

        class InlineAdmin2(InlineModelAdmin):
            pass

        self.assertEqual(inspect.getmro(InlineAdmin1)[1:],
                         inspect.getmro(InlineAdmin2)[1:])


class ContentTranslationTests(ContentTranslationTestCase):
    """
    Core aspects of content translation should function properly.

    Some of these tests may need more than one language enabled to be
    effective.
    """

    def test_switch(self):
        """
        If ``USE_MODELTRANSLATION`` is true, modeltranslation should be
        loaded.
        """
        self.assertIn('modeltranslation', settings.INSTALLED_APPS)

    def test_registration_switch(self):
        """
        Models should be registered even if ``USE_I18N`` is false (the test
        is only interesting if it is).
        """
        self.assertTrue(self.mt_settings.ENABLE_REGISTRATIONS)

    @skipUnless('mezzanine.pages' in settings.INSTALLED_APPS,
                "needs a registered, concrete Slugged subclass")
    def test_auto_population(self):
        """
        Creating objects with with a non-default language active, should not
        cause any trouble.

        In particular, loading fixtures with the default language other than
        English, should not create models with empty slugs/titles.
        """
        from mezzanine.pages.models import Page
        if self.no_fallback_pair is None:
            self.skipTest("needs a language that will not fall back")
        from_language, to_language = self.no_fallback_pair

        with override(to_language):
            slugged = Page.objects.create(title="Title")
            # Translation fields are (unnecessarily) nullable, so save works
            # even with a missing value for a language.
            slugged.save()
        with override(from_language):
            # Having an empty slug may cause issues with address resolution.
            self.assertTrue(slugged.slug)

    def test_models_registration(self):
        """
        Checks if all models that have fields looking as translatable
        are registered for translation.

        This is a reminder about adding new fields to ``translation.py``.
        Please, add fields that are detected, but should not be translatable
        to the exceptions list.
        """
        from modeltranslation.translator import NotRegistered, translator
        textual_fields_classes = (models.CharField, models.TextField)
        textual_fields_exceptions = (
            # Registering contrib models for translation, that's an idea,
            # but in general will probably have to wait for some built-in
            # content translation support.
            r"^django\.contrib\.",
            # Setting names are internal identifiers.
            r"^mezzanine\.conf\.models\.Setting\.name",
            # User-provided form values.
            r"^mezzanine\.forms\.models\.FieldEntry\.value",
            # Users translating their comments, hmmm interesting.
            r"^mezzanine\.generic\.models\.ThreadedComment",
            # TwitterQuery.type uses choices (stored value is an identifier).
            r"^mezzanine\.twitter\.models\.Query\.type",
            # Tweets are sourced from Twitter.
            r"^mezzanine\.twitter\.models.Tweet",
            # Page.in_menus is really a tuple of integers, while
            # Page.content_model is an untranslated model name.
            r"\.(in_menus|content_model)$",
            # Form email addresses; having a different accounts for
            # different languages is rather uncommon.
            r"\.(email_copies|email_from)$",
            # Before Django 1.7, South would often be an installed apps.
            r"^south\.",
            # Modeltranslation has some unregistered textual fields in tests.
            r"^modeltranslation\.",
        )
        for model in models.get_models():
            model_path = "{}.{}".format(model.__module__, model.__name__)
            textual_fields = set(
                f.name for f in model._meta.fields if
                isinstance(f, textual_fields_classes) and
                not hasattr(f, "translated_field") and
                not any(re.search(pattern, "{}.{}".format(model_path, f.name))
                        for pattern in textual_fields_exceptions))
            if not textual_fields:
                # You don't need to register models without any translatable
                # fields.
                continue
            try:
                translation_options = translator.get_options_for_model(model)
            except NotRegistered:
                self.fail(
                    "model {} has textual fields {}, but is not registered "
                    "for translation.".format(model, tuple(textual_fields)))
            registered_fields = set(translation_options.get_field_names())
            unregistered_textual_fields = textual_fields - registered_fields
            self.assertTrue(textual_fields.issubset(registered_fields),
                "some textual fields on {} are not registered for translation "
                "{}".format(model_path, tuple(unregistered_textual_fields)))

    def test_for_all_languages(self):
        """
        The provided function should be executed once for each language.
        This is supposed to also work with disabled I18N.
        """
        languages = set(self.languages)

        def function():
            languages.remove(get_language())
        for_all_languages(function)
        self.assertFalse(languages)

    def test_for_all_languages_exception(self):
        """
        The helper shouldn't hide exceptions.
        """
        def function():
            raise RuntimeError()

        with self.assertRaises(RuntimeError):
            for_all_languages(function)

    def test_disable_fallbacks(self):
        """
        The value for the current language should be visible, even if empty.
        """
        if self.fallback_pair is None:
            self.skipTest("there have to be some fallbacks defined")
        from_language, to_language = self.fallback_pair

        with override(to_language):
            # Set a value for a "default fallback" language, so we have
            # something to fallback to.
            model = Slugged(title="a")
        with override(from_language):
            model.title = ""
            self.assertEqual(model.title, "a")
            with disable_fallbacks():
                self.assertEqual(model.title, "")

    def test_disable_fallbacks_exception(self):
        """
        The helper shouldn't hide exceptions.
        """
        with self.assertRaises(RuntimeError):
            with disable_fallbacks():
                raise RuntimeError

    @skipUnless('mezzanine.pages' in settings.INSTALLED_APPS,
                "needs a registered, concrete subclass of Slugged")
    def test_slugs_generation(self):
        """
        Slugs for all languages should be generated when a ``Slugged``
        subclass is saved.
        """
        from mezzanine.pages.models import Page
        slugged = Page(title="a")
        slugged.save()

        def assert_slug():
            self.assertTrue(slugged.slug)
        with disable_fallbacks():
            for_all_languages(assert_slug)

    @skipUnless('mezzanine.pages' in settings.INSTALLED_APPS,
                "needs a registered, concrete subclass of MetaData")
    def test_descriptions_generation(self):
        """
        Descriptions should be generated for all languages when a ``MetaData``
        subclass is saved.
        """
        from mezzanine.pages.models import Page
        metadata = Page(title="a")
        metadata.save()

        def assert_description():
            self.assertTrue(metadata.description)
        with disable_fallbacks():
            for_all_languages(assert_description)

    @skipUnless('mezzanine.pages' in settings.INSTALLED_APPS,
                "needs a registered, concrete subclass of MetaData")
    def test_descriptions_independence(self):
        """
        Description for one language should not be based on description for
        another one.
        """
        if len(self.languages) < 2:
            self.skipTest("needs at least two languages enabled")

        from mezzanine.pages.models import Page
        first_language, second_language = self.languages[:2]
        with override(first_language):
            metadata = Page(title="a")
            metadata.save()
        with override(second_language):
            metadata.title = "b"
            metadata.save()
            self.assertEqual(metadata.description, "b")

    @skipUnless('mezzanine.pages' in settings.INSTALLED_APPS,
                "needs a registered, concrete subclass of Displayable")
    def test_short_url_generation(self):
        """
        Separate ``short_url`` for each language should be generated.
        """
        from mezzanine.pages.models import Page
        displayable = Page(site_id=current_site_id(), title="a")
        displayable.set_short_url()

        def assert_short_url():
            self.assertTrue(displayable.short_url)
        with disable_fallbacks():
            for_all_languages(assert_short_url)

    @skipUnless('mezzanine.pages' in settings.INSTALLED_APPS,
                "needs the Page model to be migrated and registered")
    def test_save_performance(self):
        """
        Saving models with content translation enabled should not require
        more queries than without it.
        """
        from mezzanine.pages.models import Page
        with self.assertNumQueries(4):
            page = Page(title="a")
            page.save()

    def test_admins_bases(self):
        """
        Admins of models with translatable fields should derive from one
        of translation admins.
        """
        from modeltranslation.translator import translator
        models = translator.get_registered_models()
        for model in models:
            model_admin = admin_site._registry.get(model)
            if model_admin is not None:
                self.assertIsInstance(model_admin, TranslationModelAdmin)

    @skipUnless('mezzanine.pages' in settings.INSTALLED_APPS,
                "needs a concrete subclasses of Slugged")
    def test_resavemodels_slugs(self):
        """
        Slugs that are empty should be generated.
        """
        from mezzanine.pages.models import Page
        slugged = Page(title="Title")
        slugged.save()
        # You end up with empty slugs after adding columns for new languages,
        # but to simplify things we'll just manually reset the value.
        Page.objects.all().update(slug="")
        call_command('resavemodels')
        # Django 1.8+: slugged.refresh_from_db(fields=['slug']).
        slugged = Page.objects.get(pk=slugged.pk)
        self.assertTrue(slugged.slug)

    @skipUnless('mezzanine.pages' in settings.INSTALLED_APPS,
                "needs a concrete subclasses of MetaData")
    def test_resavemodels_descriptions(self):
        """
        ``MetaData`` descriptions should be regenerated only when
        ``gen_description`` is true.
        """
        from mezzanine.pages.models import Page
        displayable_auto_desc = Page(title="Title", gen_description=True)
        displayable_auto_desc.save()
        displayable_man_desc = Page(title="Title", gen_description=False)
        displayable_man_desc.save()
        Page.objects.all().update(description="")
        call_command('resavemodels')
        # Django 1.8+: refresh_from_db(fields=['description']).
        displayable_auto_desc = Page.objects.get(pk=displayable_auto_desc.pk)
        self.assertTrue(displayable_auto_desc.description)
        displayable_man_desc = Page.objects.get(pk=displayable_man_desc.pk)
        self.assertFalse(displayable_man_desc.description)
