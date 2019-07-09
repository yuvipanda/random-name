"""Base classes for request handlers"""

import json

from http.client import responses
from tornado import web
from jupyterhub.services.auth import HubOAuthenticated, HubOAuth

from . import __version__ as binder_version


class BaseHandler(HubOAuthenticated, web.RequestHandler):
    """HubAuthenticated by default allows all successfully identified users (see allow_all property)."""

    def initialize(self):
        super().initialize()
        if self.settings['auth_enabled']:
            self.hub_auth = HubOAuth.instance(config=self.settings['traitlets_config'])

    def get_current_user(self):
        if not self.settings['auth_enabled']:
            return 'anonymous'
        return super().get_current_user()

    @property
    def template_namespace(self):
        return dict(static_url=self.static_url,
                    banner=self.settings['banner_message'],
                    **self.settings.get('template_variables', {}))

    def set_default_headers(self):
        headers = self.settings.get('headers', {})
        for header, value in headers.items():
            self.set_header(header, value)
        self.set_header("access-control-allow-headers", "cache-control")

    def get_spec_from_request(self, prefix):
        """Re-extract spec from request.path.
        Get the original, raw spec, without tornado's unquoting.
        This is needed because tornado converts 'foo%2Fbar/ref' to 'foo/bar/ref'.
        """
        idx = self.request.path.index(prefix)
        spec = self.request.path[idx + len(prefix) + 1:]
        return spec

    def get_provider(self, provider_prefix, spec):
        """Construct a provider object"""
        providers = self.settings['repo_providers']
        if provider_prefix not in providers:
            raise web.HTTPError(404, "No provider found for prefix %s" % provider_prefix)

        return providers[provider_prefix](
            config=self.settings['traitlets_config'], spec=spec)

    def render_template(self, name, **extra_ns):
        """Render an HTML page"""
        ns = {}
        ns.update(self.template_namespace)
        ns.update(extra_ns)
        template = self.settings['jinja2_env'].get_template(name)
        html = template.render(**ns)
        self.write(html)

    def extract_message(self, exc_info):
        """Return error message from exc_info"""
        exception = exc_info[1]
        # get the custom message, if defined
        try:
            return exception.log_message % exception.args
        except Exception:
            return ''

    def write_error(self, status_code, **kwargs):
        exc_info = kwargs.get('exc_info')
        message = ''
        status_message = responses.get(status_code, 'Unknown HTTP Error')
        if exc_info:
            message = self.extract_message(exc_info)

        self.render_template(
            'error.html',
            status_code=status_code,
            status_message=status_message,
            message=message,
        )

    def options(self, *args, **kwargs):
        pass


class Custom404(BaseHandler):
    """Raise a 404 error, rendering the error.html template"""

    def prepare(self):
        raise web.HTTPError(404)


class AboutHandler(BaseHandler):
    """Serve the about page"""
    async def get(self):
        self.render_template(
            "about.html",
            base_url=self.settings['base_url'],
            submit=False,
            binder_version=binder_version,
            message=self.settings['about_message'],
            google_analytics_code=self.settings['google_analytics_code'],
            google_analytics_domain=self.settings['google_analytics_domain'],
            extra_footer_scripts=self.settings['extra_footer_scripts'],
        )


class AutodetectHandler(BaseHandler):
    """Serve a just-do-the-right-thing page"""
    async def get(self):
        referrer = self.request.headers.get('Referer', '')
        self.render_template(
            "autodetect.html",
            base_url=self.settings['base_url'],
            submit=False,
            referrer=referrer,
            google_analytics_code=self.settings['google_analytics_code'],
            google_analytics_domain=self.settings['google_analytics_domain'],
            extra_footer_scripts=self.settings['extra_footer_scripts'],
        )


class VersionHandler(BaseHandler):
    """Serve information about versions running"""
    async def get(self):
        self.set_header("Content-type", "application/json")
        self.write(json.dumps(
            {
                "builder": self.settings['build_image'],
                "binderhub": binder_version,
                }
        ))
