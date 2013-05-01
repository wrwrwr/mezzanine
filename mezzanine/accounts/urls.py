
from django.conf.urls import patterns, url
from django.utils.encoding import force_text
from django.utils.functional import lazy
from django.utils import six

from mezzanine.conf import settings


ACCOUNT_URL = getattr(settings, "ACCOUNT_URL", "/account/")
SIGNUP_URL = getattr(settings, "SIGNUP_URL",
                     "/%s/signup/" % ACCOUNT_URL.strip("/"))
SIGNUP_VERIFY_URL = getattr(settings, "SIGNUP_VERIFY_URL",
                            "/%s/verify/" % ACCOUNT_URL.strip("/"))
LOGIN_URL = settings.LOGIN_URL
LOGOUT_URL = settings.LOGOUT_URL
PROFILE_URL = getattr(settings, "PROFILE_URL", "/users/")
PROFILE_UPDATE_URL = getattr(settings, "PROFILE_UPDATE_URL",
                             "/%s/update/" % ACCOUNT_URL.strip("/"))
PASSWORD_RESET_URL = getattr(settings, "PASSWORD_RESET_URL",
                             "/%s/password/reset/" % ACCOUNT_URL.strip("/"))
PASSWORD_RESET_VERIFY_URL = getattr(settings, "PASSWORD_RESET_VERIFY_URL",
                                    "/%s/password/verify/" %
                                    ACCOUNT_URL.strip("/"))

_verify_pattern = "/(?P<uidb36>[-\w]+)/(?P<token>[-\w]+)"
_slash = "/" if settings.APPEND_SLASH else ""


def _path_format(path, additional=""):
    path = force_text(path).strip("/")
    return "^%s%s%s$" % (path, additional, _slash)
_path_format_lazy = lazy(_path_format, six.text_type)


urlpatterns = patterns("mezzanine.accounts.views",
    url(_path_format_lazy(LOGIN_URL), "login", name="login"),
    url(_path_format_lazy(LOGOUT_URL), "logout", name="logout"),
    url(_path_format_lazy(SIGNUP_URL), "signup", name="signup"),
    url(_path_format_lazy(SIGNUP_VERIFY_URL, _verify_pattern),
        "signup_verify", name="signup_verify"),
    url(_path_format_lazy(PROFILE_UPDATE_URL),
        "profile_update", name="profile_update"),
    url(_path_format_lazy(PASSWORD_RESET_URL),
        "password_reset", name="mezzanine_password_reset"),
    url(_path_format_lazy(PASSWORD_RESET_VERIFY_URL, _verify_pattern),
        "password_reset_verify", name="password_reset_verify"),
    url(_path_format_lazy(ACCOUNT_URL),
        "account_redirect", name="account_redirect"),
)

if settings.ACCOUNTS_PROFILE_VIEWS_ENABLED:
    urlpatterns += patterns("mezzanine.accounts.views",
        url(_path_format_lazy(PROFILE_URL),
            "profile_redirect", name="profile_redirect"),
        url(_path_format_lazy(PROFILE_URL, "/(?P<username>.*)"),
            "profile", name="profile"),
    )
