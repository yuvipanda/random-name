"""
Interaction with the Docker Registry
"""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from urllib.parse import urlparse

import boto3
import kubernetes.client
import kubernetes.config
from tornado import gen, httpclient
from tornado.httputil import url_concat
from traitlets import default, Dict, Unicode, Any, Integer
from traitlets.config import LoggingConfigurable

DEFAULT_DOCKER_REGISTRY_URL = "https://registry.hub.docker.com"
DEFAULT_DOCKER_AUTH_URL = "https://index.docker.io/v1"


class DockerRegistry(LoggingConfigurable):
    url = Unicode(
        DEFAULT_DOCKER_REGISTRY_URL,
        help="""
        Docker registry url.

        Default: retrieved from docker config.json

        Only set this if:
        - not using docker hub, and
        - more than one registry is configured in docker config.json
        """,
        config=True,
    )

    @default("url")
    def _default_url(self):
        cfg = self._docker_config
        auths = cfg.get("auths", {})
        if not auths:
            return DEFAULT_DOCKER_REGISTRY_URL

        # default to first entry in docker config.json auths
        auth_config_url = next(iter(auths.keys()))
        if "://" not in auth_config_url:
            # auth key can be just a hostname,
            # which assumes https
            auth_config_url = "https://" + auth_config_url

        if auth_config_url.rstrip("/") == DEFAULT_DOCKER_AUTH_URL:
            # default docker config key is the v1 registry,
            # but we will talk to the v2 api
            return DEFAULT_DOCKER_REGISTRY_URL

        return auth_config_url

    auth_config_url = Unicode(
        DEFAULT_DOCKER_AUTH_URL,
        help="""
        Docker auth configuration url.

        Used to lookup auth data in docker config.json.

        Not used if url, username, and password are set.

        Default: same as url

        Only set if:
        - Not using Docker Hub
        - registry url is not the auth key in docker config.json
        """,
        config=True,
    )

    @default("auth_config_url")
    def _auth_config_url_default(self):
        url = urlparse(self.url)
        cfg = self._docker_config
        auths = cfg.get("auths", {})
        # check for our url in docker config.json
        # there can be some variation, so try a few things.

        # in ~all cases, the registry url will appear in config.json
        if self.url in auths:
            # this will
            return self.url
        # ...but the config key is allowed to lack https://, so check just hostname
        if url.hostname in auths:
            return url.hostname
        # default docker special-case, where auth and registry urls are different
        if ("." + url.hostname).endswith((".docker.io", ".docker.com")):
            return DEFAULT_DOCKER_AUTH_URL

        # url not found, leave the most likely default
        return self.url

    docker_config_path = Unicode(
        os.path.join(
            os.environ.get("DOCKER_CONFIG", os.path.expanduser("~/.docker")),
            "config.json",
        ),
        help=""""
        path to docker config.json

        Default: ~/.docker/config.json (respects $DOCKER_CONFIG if set)
        """,
        config=True,
    )
    _docker_config = Dict()

    @default("_docker_config")
    def _load_docker_config(self):
        if not os.path.exists(self.docker_config_path):
            self.log.warning("No docker config at %s", self.docker_config_path)
            return {}
        self.log.info("Loading docker config %s", self.docker_config_path)
        with open(self.docker_config_path) as f:
            return json.load(f)

    token_url = Unicode(
        help="""
        URL to request docker registry authentication token.

        No need to set if using Docker Hub or gcr.io
        """,
        config=True,
    )

    @default("token_url")
    def _default_token_url(self):
        url = urlparse(self.url)
        if ("." + url.hostname).endswith(".gcr.io"):
            return "https://{0}/v2/token?service={0}".format(url.hostname)
        elif self.url.endswith(".docker.com"):
            return "https://auth.docker.io/token?service=registry.docker.io"
        else:
            # is gcr.io's token url common? If so, it might be worth defaulting
            # to https://registry.host/v2/token?service=registry.host
            return ""

    username = Unicode(
        help="""
        Username for authenticating with docker registry

        Default: retrieved from docker config.json.
        """,
        config=True,
    )

    @default("username")
    def _default_username(self):
        b64_auth = None
        if self.auth_config_url in self._docker_config.get("auths", {}):
            b64_auth = self._docker_config["auths"][self.auth_config_url].get("auth")

        if not b64_auth:
            self.log.warning(
                "No username for docker registry at %s", self.auth_config_url
            )
            return ""

        return (
            base64.b64decode(b64_auth.encode("utf-8")).decode("utf-8").split(":", 1)[0]
        )

    password = Unicode(
        help="""
        Password for authenticating with docker registry

        Default: retrieved from docker config.json.
        """,
        config=True,
    )

    @default("password")
    def _default_password(self):
        b64_auth = None
        if self.auth_config_url in self._docker_config.get("auths", {}):
            b64_auth = self._docker_config["auths"][self.auth_config_url].get("auth")

        if not b64_auth:
            self.log.warning(
                "No password for docker registry at %s", self.auth_config_url
            )
            return ""

        return (
            base64.b64decode(b64_auth.encode("utf-8")).decode("utf-8").split(":", 1)[1]
        )

    @gen.coroutine
    def get_image_manifest(self, image, tag):
        client = httpclient.AsyncHTTPClient()
        url = "{}/v2/{}/manifests/{}".format(self.url, image, tag)
        # first, get a token to perform the manifest request
        if self.token_url:
            auth_req = httpclient.HTTPRequest(
                url_concat(self.token_url, {"scope": "repository:{}:pull".format(image)}),
                auth_username=self.username,
                auth_password=self.password,
            )
            auth_resp = yield client.fetch(auth_req)
            response_body = json.loads(auth_resp.body.decode("utf-8", "replace"))

            if "token" in response_body.keys():
                token = response_body["token"]
            elif "access_token" in response_body.keys():
                token = response_body["access_token"]

            req = httpclient.HTTPRequest(url,
                headers={"Authorization": "Bearer {}".format(token)},
            )
        else:
            # Use basic HTTP auth (htpasswd)
            req = httpclient.HTTPRequest(url,
                auth_username=self.username,
                auth_password=self.password,
            )

        try:
            resp = yield client.fetch(req)
        except httpclient.HTTPError as e:
            if e.code == 404:
                # 404 means it doesn't exist
                return None
            else:
                raise
        else:
            return json.loads(resp.body.decode("utf-8"))


class AWSElasticContainerRegistry(DockerRegistry):
    aws_region = Unicode(
        config=True,
        help="""
        AWS region for ECR service
        """,
    )

    ecr_client = Any()

    @default("ecr_client")
    def _get_ecr_client(self):
        return boto3.client("ecr", region_name=self.aws_region)

    username = "AWS"

    executor_threads = Integer(
        5,
        config=True,
        help="""The number of threads to use for blocking calls

        Should generaly be a small number because we don't
        care about high concurrency here, just not blocking the webserver.
        This executor is not used for long-running tasks (e.g. builds).
        """,
    )

    executor = Any()

    @default("executor")
    def _get_executor(self):
        return ThreadPoolExecutor(self.executor_threads)

    kube_client = Any()

    @default("kube_client")
    def _get_kube_client(self):
        kubernetes.config.load_incluster_config()
        return kubernetes.client.CoreV1Api()

    async def get_image_manifest(self, image, tag):
        image = image.split("/", 1)[1]
        await asyncio.wrap_future(self.executor.submit(self._pre_get_image_manifest, image, tag))
        return await super().get_image_manifest(image, tag)

    def _pre_get_image_manifest(self, image, tag):
        self._create_repository(image, tag)
        self._refresh_password()

    def _create_repository(self, image, tag):
        try:
            self.ecr_client.create_repository(repositoryName=image)
            self.log.info("ECR repo {} created".format(image))
        except self.ecr_client.exceptions.RepositoryAlreadyExistsException:
            self.log.info("ECR repo {} already exists".format(image))

    # An IAM principal is used to generate an auth token that is valid for 12 hours
    # ref: https://docs.aws.amazon.com/AmazonECR/latest/userguide/Registries.html
    # TODO: cache auth if not expired - authorizationData[i]["expiresAt"]
    def _refresh_password(self):
        auths = self.ecr_client.get_authorization_token()["authorizationData"]
        auth = next(x for x in auths if x["proxyEndpoint"] == self.url)
        self._patch_docker_config_secret(auth)
        self.password = base64.b64decode(auth['authorizationToken']).decode("utf-8").split(':')[1]
    
    def _patch_docker_config_secret(self, auth):
        """Patch binder-push-secret"""
        secret_data = {"auths": {self.url: {"auth": auth["authorizationToken"]}}}
        secret_data = base64.b64encode(json.dumps(secret_data).encode("utf8")).decode(
            "utf8"
        )
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as f:
            namespace = f.read()
        self.kube_client.patch_namespaced_secret(
            "binder-push-secret", namespace, {"data": {"config.json": secret_data}}
        )
