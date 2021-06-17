"""
Main handler classes for requests
"""
import urllib.parse

from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.web import HTTPError, authenticated
from tornado.httputil import url_concat
from tornado.log import app_log

from .base import BaseHandler

SPEC_NAMES = {
    "gh": "GitHub",
    "gist": "Gist",
    "gl": "GitLab",
    "git": "Git repo",
    "zenodo": "Zenodo",
    "figshare": "Figshare",
    "hydroshare": "Hydroshare",
    "dataverse": "Dataverse",
}


class MainHandler(BaseHandler):
    """Main handler for requests"""

    @authenticated
    def get(self):
        self.render_template(
            "index.html",
            badge_base_url=self.get_badge_base_url(),
            base_url=self.settings['base_url'],
            submit=False,
            google_analytics_code=self.settings['google_analytics_code'],
            google_analytics_domain=self.settings['google_analytics_domain'],
            extra_footer_scripts=self.settings['extra_footer_scripts'],
            repo_providers=self.settings['repo_providers'],
        )


class ParameterizedMainHandler(BaseHandler):
    """Main handler that allows different parameter settings"""

    @authenticated
    async def get(self, provider_prefix, _unescaped_spec):
        prefix = '/v2/' + provider_prefix
        spec = self.get_spec_from_request(prefix)
        spec = spec.rstrip("/")
        try:
            await self.get_provider(provider_prefix, spec=spec)
        except HTTPError:
            raise
        except Exception as e:
            app_log.error(
                "Failed to construct provider for %s/%s",
                provider_prefix, spec,
            )
            # FIXME: 400 assumes it's the user's fault (?)
            # maybe we should catch a special InvalidSpecError here
            raise HTTPError(400, str(e))

        provider_spec = f'{provider_prefix}/{spec}'
        social_desc = f"{SPEC_NAMES[provider_prefix]}: {spec}"
        nbviewer_url = None
        if provider_prefix == "gh":
            # we can only produce an nbviewer URL for github right now
            nbviewer_url = 'https://nbviewer.jupyter.org/github'
            org, repo_name, ref = spec.split('/', 2)
            # NOTE: tornado unquotes query arguments too -> notebooks%2Findex.ipynb becomes notebooks/index.ipynb
            filepath = self.get_argument('filepath', '').lstrip('/')

            # Check if we have a JupyterLab + file path, if so then use it for the filepath
            urlpath = self.get_argument('urlpath', '').lstrip('/')
            if urlpath.startswith("lab") and "/tree/" in urlpath:
                filepath = urlpath.split('tree/', 1)[-1]

            blob_or_tree = 'blob' if filepath else 'tree'
            nbviewer_url = f'{nbviewer_url}/{org}/{repo_name}/{blob_or_tree}/{ref}/{filepath}'

            # Check if the nbviewer URL is valid and would display something
            # useful to the reader, if not we don't show it
            client = AsyncHTTPClient()
            # quote any unicode characters in the URL
            proto, rest = nbviewer_url.split("://")
            rest = urllib.parse.quote(rest)

            request = HTTPRequest(proto + "://" + rest,
                                  method="HEAD",
                                  user_agent="BinderHub",
                                  )
            response = await client.fetch(request, raise_error=False)
            if response.code >= 400:
                nbviewer_url = None

        self.render_template(
            "loading.html",
            base_url=self.settings['base_url'],
            badge_base_url=self.get_badge_base_url(),
            provider_spec=provider_spec,
            social_desc=social_desc,
            nbviewer_url=nbviewer_url,
            # urlpath=self.get_argument('urlpath', None),
            submit=True,
            google_analytics_code=self.settings['google_analytics_code'],
            google_analytics_domain=self.settings['google_analytics_domain'],
            extra_footer_scripts=self.settings['extra_footer_scripts'],
        )


class LegacyRedirectHandler(BaseHandler):
    """Redirect handler from legacy Binder"""

    @authenticated
    def get(self, user, repo, urlpath=None):
        url = '/v2/gh/{user}/{repo}/master'.format(user=user, repo=repo)
        if urlpath is not None and urlpath.strip('/'):
            url = url_concat(url, dict(urlpath=urlpath))
        self.redirect(url)
