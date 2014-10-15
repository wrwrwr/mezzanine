"""
Used as default urls for tests not deriving from the mezzanine ``TestCase``
(``mezzanine.utils.tests.TestCase``) to enable testing of ``django.contrib``
apps (which require empty patterns and add their urls on their own).
"""
from django.conf.urls import patterns


urlpatterns = patterns("")
