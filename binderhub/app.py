"""
The binderhub application
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import re
from glob import glob
from urllib.parse import urlparse

import kubernetes.client
import kubernetes.config
from jinja2 import Environment, FileSystemLoader, PrefixLoader, ChoiceLoader
from tornado.httpclient import AsyncHTTPClient
from tornado.httpserver import HTTPServer
import tornado.ioloop
import tornado.options
import tornado.log
from tornado.log import app_log
import tornado.web
from traitlets import Unicode, Integer, Bool, Dict, validate, TraitError, default
from traitlets.config import Application
from jupyterhub.services.auth import HubOAuthCallbackHandler

from .base import AboutHandler, Custom404, VersionHandler
from .build import Build
from .builder import BuildHandler
from .launcher import Launcher
from .registry import DockerRegistry
from .main import MainHandler, ParameterizedMainHandler, LegacyRedirectHandler
from .repoproviders import GitHubRepoProvider, GitRepoProvider, GitLabRepoProvider, GistRepoProvider
from .metrics import MetricsHandler

from .utils import ByteSpecification, url_path_join
from .events import EventLog


HERE = os.path.dirname(os.path.abspath(__file__))


class BinderHub(Application):
    """An Application for starting a builder."""

    @default('log_level')
    def _log_level(self):
        return logging.INFO

    aliases = {
        'log-level': 'Application.log_level',
        'f': 'BinderHub.config_file',
        'config': 'BinderHub.config_file',
        'port': 'BinderHub.port',
    }

    flags = {
        'debug': (
            {'BinderHub': {'debug': True}},
            "Enable debug HTTP serving & debug logging"
        )
    }

    config_file = Unicode(
        'binderhub_config.py',
        help="""
        Config file to load.

        If a relative path is provided, it is taken relative to current directory
        """,
        config=True
    )

    google_analytics_code = Unicode(
        None,
        allow_none=True,
        help="""
        The Google Analytics code to use on the main page.

        Note that we'll respect Do Not Track settings, despite the fact that GA does not.
        We will not load the GA scripts on browsers with DNT enabled.
        """,
        config=True
    )

    google_analytics_domain = Unicode(
        'auto',
        help="""
        The Google Analytics domain to use on the main page.

        By default this is set to 'auto', which sets it up for current domain and all
        subdomains. This can be set to a more restrictive domain here for better privacy
        """,
        config=True
    )

    about_message = Unicode(
        '',
        help="""
        Additional message to display on the about page.

        Will be directly inserted into the about page's source so you can use
        raw HTML.
        """,
        config=True
    )

    extra_footer_scripts = Dict(
        {},
        help="""
        Extra bits of JavaScript that should be loaded in footer of each page.

        Only the values are set up as scripts. Keys are used only
        for sorting.

        Omit the <script> tag. This should be primarily used for
        analytics code.
        """,
        config=True
    )

    base_url = Unicode(
        '/',
        help="The base URL of the entire application",
        config=True)

    @validate('base_url')
    def _valid_base_url(self, proposal):
        if not proposal.value.startswith('/'):
            proposal.value = '/' + proposal.value
        if not proposal.value.endswith('/'):
            proposal.value = proposal.value + '/'
        return proposal.value

    auth_enabled = Bool(
        False,
        help="""If JupyterHub authentication enabled,
        require user to login (don't create temporary users during launch) and
        start the new server for the logged in user.""",
        config=True)

    use_named_servers = Bool(
        False,
        help="Use named servers when authentication is enabled.",
        config=True)

    port = Integer(
        8585,
        help="""
        Port for the builder to listen on.
        """,
        config=True
    )

    appendix = Unicode(
        help="""
        Appendix to pass to repo2docker

        A multi-line string of Docker directives to run.
        Since the build context cannot be affected,
        ADD will typically not be useful.

        This should be a Python string template.
        It will be formatted with at least the following names available:

        - binder_url: the shareable URL for the current image
          (e.g. for sharing links to the current Binder)
        - repo_url: the repository URL used to build the image
        """,
        config=True,
    )

    use_registry = Bool(
        True,
        help="""
        Set to true to push images to a registry & check for images in registry.

        Set to false to use only local docker images. Useful when running
        in a single node.
        """,
        config=True
    )

    per_repo_quota = Integer(
        0,
        help="""
        Maximum number of concurrent users running from a given repo.

        Limits the amount of Binder that can be consumed by a single repo.

        0 (default) means no quotas.
        """,
        config=True,
    )

    log_tail_lines = Integer(
        100,
        help="""
        Limit number of log lines to show when connecting to an already running build.
        """,
        config=True,
    )

    push_secret = Unicode(
        'binder-push-secret',
        allow_none=True,
        help="""
        A kubernetes secret object that provides credentials for pushing built images.
        """,
        config=True
    )

    image_prefix = Unicode(
        "",
        help="""
        Prefix for all built docker images.

        If you are pushing to gcr.io, this would start with:
            gcr.io/<your-project-name>/

        Set according to whatever registry you are pushing to.

        Defaults to "", which is probably not what you want :)
        """,
        config=True
    )

    build_memory_limit = ByteSpecification(
        0,
        help="""
        Max amount of memory allocated for each image build process.

        0 sets no limit.

        This is used as both the memory limit & request for the pod
        that is spawned to do the building, even though the pod itself
        will not be using that much memory since the docker building is
        happening outside the pod. However, it makes kubernetes aware of
        the resources being used, and lets it schedule more intelligently.
        """,
        config=True
    )

    debug = Bool(
        False,
        help="""
        Turn on debugging.
        """,
        config=True
    )

    build_docker_host = Unicode(
        "/var/run/docker.sock",
        config=True,
        help="""
        The docker URL repo2docker should use to build the images.

        Currently, only paths are supported, and they are expected to be available on
        all the hosts.
        """
    )
    @validate('build_docker_host')
    def docker_build_host_validate(self, proposal):
        parts = urlparse(proposal.value)
        if parts.scheme != 'unix' or parts.netloc != '':
            raise TraitError("Only unix domain sockets on same node are supported for build_docker_host")
        return proposal.value

    hub_api_token = Unicode(
        help="""API token for talking to the JupyterHub API""",
        config=True,
    )
    @default('hub_api_token')
    def _default_hub_token(self):
        return os.environ.get('JUPYTERHUB_API_TOKEN', '')

    hub_url = Unicode(
        help="""
        The base URL of the JupyterHub instance where users will run.

        e.g. https://hub.mybinder.org/
        """,
        config=True,
    )
    @validate('hub_url')
    def _add_slash(self, proposal):
        """trait validator to ensure hub_url ends with a trailing slash"""
        if proposal.value is not None and not proposal.value.endswith('/'):
            return proposal.value + '/'
        return proposal.value

    build_namespace = Unicode(
        'default',
        help="""
        Kubernetes namespace to spawn build pods in.

        Note that the push_secret must refer to a secret in this namespace.
        """,
        config=True
    )

    build_image = Unicode(
        'jupyter/repo2docker:0.8.0',
        help="""
        The repo2docker image to be used for doing builds
        """,
        config=True
    )

    build_node_selector = Dict(
        {},
        config=True,
        help="""
        Select the node where build pod runs on.
        """
    )

    repo_providers = Dict(
        {
            'gh': GitHubRepoProvider,
            'gist': GistRepoProvider,
            'git': GitRepoProvider,
            'gl': GitLabRepoProvider,
        },
        config=True,
        help="""
        List of Repo Providers to register and try
        """
    )
    concurrent_build_limit = Integer(
        32,
        config=True,
        help="""The number of concurrent builds to allow."""
    )
    executor_threads = Integer(
        5,
        config=True,
        help="""The number of threads to use for blocking calls

        Should generaly be a small number because we don't
        care about high concurrency here, just not blocking the webserver.
        This executor is not used for long-running tasks (e.g. builds).
        """,
    )
    build_cleanup_interval = Integer(
        60,
        config=True,
        help="""Interval (in seconds) for how often stopped build pods will be deleted."""
    )
    build_max_age = Integer(
        3600 * 4,
        config=True,
        help="""Maximum age of builds

        Builds that are still running longer than this
        will be killed.
        """
    )

    # FIXME: Come up with a better name for it?
    builder_required = Bool(
        True,
        config=True,
        help="""
        If binderhub should try to continue to run without a working build infrastructure.

        Build infrastructure is kubernetes cluster + docker. This is useful for pure HTML/CSS/JS local development.
        """
    )

    tornado_settings = Dict(
        config=True,
        help="""
        additional settings to pass through to tornado.

        can include things like additional headers, etc.
        """
    )

    template_variables = Dict(
        config=True,
        help="Extra variables to supply to jinja templates when rendering.",
    )

    template_path = Unicode(
        help="Path to search for custom jinja templates, before using the default templates.",
        config=True,
    )

    @default('template_path')
    def _template_path_default(self):
        return os.path.join(HERE, 'templates')

    extra_static_path = Unicode(
        help='Path to search for extra static files.',
        config=True,
    )

    extra_static_url_prefix = Unicode(
        '/extra_static/',
        help='Url prefix to serve extra static files.',
        config=True,
    )

    @staticmethod
    def add_url_prefix(prefix, handlers):
        """add a url prefix to handlers"""
        for i, tup in enumerate(handlers):
            lis = list(tup)
            lis[0] = url_path_join(prefix, tup[0])
            handlers[i] = tuple(lis)
        return handlers

    def init_pycurl(self):
        try:
            AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
        except ImportError as e:
            self.log.debug("Could not load pycurl: %s\npycurl is recommended if you have a large number of users.", e)
        # set max verbosity of curl_httpclient at INFO
        # because debug-logging from curl_httpclient
        # includes every full request and response
        if self.log_level < logging.INFO:
            curl_log = logging.getLogger('tornado.curl_httpclient')
            curl_log.setLevel(logging.INFO)

    def initialize(self, *args, **kwargs):
        """Load configuration settings."""
        super().initialize(*args, **kwargs)
        self.load_config_file(self.config_file)
        # hook up tornado logging
        if self.debug:
            self.log_level = logging.DEBUG
        tornado.options.options.logging = logging.getLevelName(self.log_level)
        tornado.log.enable_pretty_logging()
        self.log = tornado.log.app_log

        self.init_pycurl()

        # initialize kubernetes config
        if self.builder_required:
            try:
                kubernetes.config.load_incluster_config()
            except kubernetes.config.ConfigException:
                kubernetes.config.load_kube_config()
            self.tornado_settings["kubernetes_client"] = self.kube_client = kubernetes.client.CoreV1Api()

        else:
            self.tornado_settings["kubernetes_client"] = None


        # times 2 for log + build threads
        self.build_pool = ThreadPoolExecutor(self.concurrent_build_limit * 2)
        # default executor for asyncifying blocking calls (e.g. to kubernetes, docker).
        # this should not be used for long-running requests
        self.executor = ThreadPoolExecutor(self.executor_threads)

        jinja_options = dict(autoescape=True, )
        template_paths = [self.template_path]
        base_template_path = self._template_path_default()
        if base_template_path not in template_paths:
            # add base templates to the end, so they are looked up at last after custom templates
            template_paths.append(base_template_path)
        loader = ChoiceLoader([
            # first load base templates with prefix
            PrefixLoader({'templates': FileSystemLoader([base_template_path])}, '/'),
            # load all templates
            FileSystemLoader(template_paths)
        ])
        jinja_env = Environment(loader=loader, **jinja_options)
        if self.use_registry and self.builder_required:
            registry = DockerRegistry(parent=self)
        else:
            registry = None

        self.launcher = Launcher(
            parent=self,
            hub_url=self.hub_url,
            hub_api_token=self.hub_api_token,
            create_user=not self.auth_enabled,
        )

        self.event_log = EventLog(parent=self)

        for schema_file in glob(os.path.join(HERE, 'event-schemas','*.json')):
            with open(schema_file) as f:
                self.event_log.register_schema(json.load(f))

        self.tornado_settings.update({
            "push_secret": self.push_secret,
            "image_prefix": self.image_prefix,
            "debug": self.debug,
            'launcher': self.launcher,
            'appendix': self.appendix,
            "build_namespace": self.build_namespace,
            "build_image": self.build_image,
            'build_node_selector': self.build_node_selector,
            'build_pool': self.build_pool,
            'log_tail_lines': self.log_tail_lines,
            'per_repo_quota': self.per_repo_quota,
            'repo_providers': self.repo_providers,
            'use_registry': self.use_registry,
            'registry': registry,
            'traitlets_config': self.config,
            'google_analytics_code': self.google_analytics_code,
            'google_analytics_domain': self.google_analytics_domain,
            'about_message': self.about_message,
            'extra_footer_scripts': self.extra_footer_scripts,
            'jinja2_env': jinja_env,
            'build_memory_limit': self.build_memory_limit,
            'build_docker_host': self.build_docker_host,
            'base_url': self.base_url,
            "static_path": os.path.join(HERE, "static"),
            'static_url_prefix': url_path_join(self.base_url, 'static/'),
            'template_variables': self.template_variables,
            'executor': self.executor,
            'auth_enabled': self.auth_enabled,
            'use_named_servers': self.use_named_servers,
            'event_log': self.event_log
        })
        if self.auth_enabled:
            self.tornado_settings['cookie_secret'] = os.urandom(32)

        handlers = [
            (r'/metrics', MetricsHandler),
            (r'/versions', VersionHandler),
            (r"/build/([^/]+)/(.+)", BuildHandler),
            (r"/v2/([^/]+)/(.+)", ParameterizedMainHandler),
            (r"/repo/([^/]+)/([^/]+)(/.*)?", LegacyRedirectHandler),
            # for backward-compatible mybinder.org badge URLs
            # /assets/images/badge.svg
            (r'/assets/(images/badge\.svg)',
                tornado.web.StaticFileHandler,
                {'path': self.tornado_settings['static_path']}),
            # /badge.svg
            (r'/(badge\.svg)',
                tornado.web.StaticFileHandler,
                {'path': os.path.join(self.tornado_settings['static_path'], 'images')}),
            # /badge_logo.svg
            (r'/(badge\_logo\.svg)',
                tornado.web.StaticFileHandler,
                {'path': os.path.join(self.tornado_settings['static_path'], 'images')}),
            # /favicon_XXX.ico
            (r'/(favicon\_fail\.ico)',
                tornado.web.StaticFileHandler,
                {'path': os.path.join(self.tornado_settings['static_path'], 'images')}),
            (r'/(favicon\_success\.ico)',
                tornado.web.StaticFileHandler,
                {'path': os.path.join(self.tornado_settings['static_path'], 'images')}),
            (r'/(favicon\_building\.ico)',
                tornado.web.StaticFileHandler,
                {'path': os.path.join(self.tornado_settings['static_path'], 'images')}),
            (r'/about', AboutHandler),
            (r'/', MainHandler),
            (r'.*', Custom404),
        ]
        handlers = self.add_url_prefix(self.base_url, handlers)
        if self.extra_static_path:
            handlers.insert(-1, (re.escape(url_path_join(self.base_url, self.extra_static_url_prefix)) + r"(.*)",
                                 tornado.web.StaticFileHandler,
                                 {'path': self.extra_static_path}))
        if self.auth_enabled:
            oauth_redirect_uri = os.getenv('JUPYTERHUB_OAUTH_CALLBACK_URL') or \
                                 url_path_join(self.base_url, 'oauth_callback')
            oauth_redirect_uri = urlparse(oauth_redirect_uri).path
            handlers.insert(-1, (re.escape(oauth_redirect_uri), HubOAuthCallbackHandler))
        self.tornado_app = tornado.web.Application(handlers, **self.tornado_settings)

    def stop(self):
        self.http_server.stop()
        self.build_pool.shutdown()

    async def watch_build_pods(self):
        """Watch build pods

        Every build_cleanup_interval:
        - delete stopped build pods
        - delete running build pods older than build_max_age
        """
        while True:
            try:
                await asyncio.wrap_future(
                    self.executor.submit(
                        lambda: Build.cleanup_builds(
                            self.kube_client,
                            self.build_namespace,
                            self.build_max_age,
                        )
                    )
                )
            except Exception:
                app_log.exception("Failed to cleanup build pods")
            await asyncio.sleep(self.build_cleanup_interval)

    def start(self, run_loop=True):
        self.log.info("BinderHub starting on port %i", self.port)
        self.http_server = HTTPServer(
            self.tornado_app,
            xheaders=True,
        )
        self.http_server.listen(self.port)
        if self.builder_required:
            asyncio.ensure_future(self.watch_build_pods())
        if run_loop:
            tornado.ioloop.IOLoop.current().start()


main = BinderHub.launch_instance

if __name__ == '__main__':
    main()
