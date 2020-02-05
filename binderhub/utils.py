"""Miscellaneous utilities"""
from collections import OrderedDict
from hashlib import blake2b

from traitlets import Integer, TraitError
from tornado.httpclient import AsyncHTTPClient, HTTPRequest, HTTPResponse
from typing import Any, Union, Awaitable
from urllib.parse import urlparse
import ipaddress
import re
import os


def blake2b_hash_as_int(b):
    """Compute digest of the bytes `b` using the Blake2 hash function.

    Returns a unsigned 64bit integer.
    """
    return int.from_bytes(blake2b(b, digest_size=8).digest(), "big")


def rendezvous_rank(buckets, key):
    """Rank the buckets for a given key using Rendez-vous hashing

    Each bucket is scored for the specified key. The return value is a list of
    all buckets, sorted in decreasing order (highest ranked first).
    """
    ranking = []
    for bucket in buckets:
        # The particular hash function doesn't matter a lot, as long as it is
        # one that maps the key to a fixed sized value and distributes the keys
        # uniformly across the output space
        score = blake2b_hash_as_int(
            b"%s-%s" % (str(key).encode(), str(bucket).encode())
        )
        ranking.append((score, bucket))

    return [b for (s, b) in sorted(ranking, reverse=True)]


class ByteSpecification(Integer):
    """
    Allow easily specifying bytes in units of 1024 with suffixes

    Suffixes allowed are:
      - K -> Kilobyte
      - M -> Megabyte
      - G -> Gigabyte
      - T -> Terabyte

    Stolen from JupyterHub
    """

    UNIT_SUFFIXES = {
        "K": 1024,
        "M": 1024 * 1024,
        "G": 1024 * 1024 * 1024,
        "T": 1024 * 1024 * 1024 * 1024,
    }

    # Default to allowing None as a value
    allow_none = True

    def validate(self, obj, value):
        """
        Validate that the passed in value is a valid memory specification

        It could either be a pure int, when it is taken as a byte value.
        If it has one of the suffixes, it is converted into the appropriate
        pure byte value.
        """
        if isinstance(value, (int, float)):
            return int(value)

        try:
            num = float(value[:-1])
        except ValueError:
            raise TraitError(
                "{val} is not a valid memory specification. Must be an int or a string with suffix K, M, G, T".format(
                    val=value
                )
            )
        suffix = value[-1]
        if suffix not in self.UNIT_SUFFIXES:
            raise TraitError(
                "{val} is not a valid memory specification. Must be an int or a string with suffix K, M, G, T".format(
                    val=value
                )
            )
        else:
            return int(float(num) * self.UNIT_SUFFIXES[suffix])


class Cache(OrderedDict):
    """Basic LRU Cache with get/set"""

    def __init__(self, max_size=1024):
        self.max_size = max_size

    def get(self, key, default=None):
        """Get an item from the cache

        same as dict.get
        """
        if key in self:
            self.move_to_end(key)
        return super().get(key, default)

    def set(self, key, value):
        """Store an item in the cache

        - if already there, moves to the most recent
        - if full, delete the oldest item
        """
        self[key] = value
        self.move_to_end(key)
        if len(self) > self.max_size:
            first_key = next(iter(self))
            self.pop(first_key)


class ProxiedAsyncHTTPClient():
    """wrapper for automatic proxy support in tornado's non-blocking HTTP client.

    see tornado.httplib.AsyncHTTPClient for usage/documentation
    """
    def __init__(self):
        self.client = AsyncHTTPClient()

        # use the first found proxy environment variable
        self.http_proxy_host = None
        self.http_proxy_port = None
        for proxy_var in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
            try:
                parsed_proxy = urlparse(os.environ[proxy_var])
                self.http_proxy_host = parsed_proxy.hostname
                proxy_port = parsed_proxy.port
                if proxy_port:  # can be None
                    self.http_proxy_port = int(proxy_port)
                else:
                    self.http_proxy_port = 443 if parsed_proxy.scheme == 'https' else 80
                break
            except KeyError:
                pass

        # sort no_proxy environment variable into CIDR ranges (e.g. 10.0.0.0/8)
        # and "simple" matches (e.g. my-institution.org or 10.1.2.3)
        self.no_proxy_simple = []
        self.no_proxy_cidr = []
        no_proxy = None
        for no_proxy_var in ['NO_PROXY', 'no_proxy']:
            try:
                no_proxy = os.environ[no_proxy_var]
            except KeyError:
                pass
        if no_proxy:
            for no_proxy_part in no_proxy.split(','):
                if self._is_cidr_range(no_proxy_part):
                    self.no_proxy_cidr.append(no_proxy_part)
                else:
                    self.no_proxy_simple.append(no_proxy_part)

    @staticmethod
    def _is_cidr_range(test_string):
        range_parts = test_string.split('/')
        if len(range_parts) != 2:
            return False
        ip, suffix = range_parts
        ip_is_valid = ProxiedAsyncHTTPClient._is_ip(ip)
        suffix_is_valid = bool(re.fullmatch('(?:[0-9]|[12][0-9]|3[0-2])', suffix))
        return ip_is_valid and suffix_is_valid

    @staticmethod
    def _is_ip(test_string):
        ip_digit = '(?:1[0-9]?[0-9]|[1-9][0-9]|[0-9]|2[0-4][0-9]|25[0-5])'
        return bool(re.fullmatch(rf'{ip_digit}\.{ip_digit}\.{ip_digit}\.{ip_digit}', test_string))

    def fetch(
        self,
        request: Union[str, "HTTPRequest"],
        raise_error: bool = True,
        **kwargs: Any
    ) -> Awaitable["HTTPResponse"]:
        """Executes a request, asynchronously returning an `HTTPResponse`.

        see tornado.httpclient.AsyncHTTPClient.fetch for documentation
        """
        # convert request argument into HTTPRequest if necessary
        if isinstance(request, str):
            request = HTTPRequest(url=request, **kwargs)

        # determine correct proxy host and port
        parsed_url = urlparse(request.url)
        if self.http_proxy_host and parsed_url.scheme in ('http', 'https'):
            bypass_proxy = False
            url_hostname = str(parsed_url.hostname)
            if ProxiedAsyncHTTPClient._is_ip(url_hostname):
                for no_proxy_cidr in self.no_proxy_cidr:
                    if ipaddress.ip_address(url_hostname) in ipaddress.ip_network(no_proxy_cidr):
                        bypass_proxy = True
                        break
            for no_proxy_simple in self.no_proxy_simple:
                escaped_no_proxy = re.escape(no_proxy_simple)
                # try to match as full domain or last part of it
                # for example: when "my-institution.org" is given as part of no_proxy, try to match
                # "my-institution.org" and subdomains like "www.my-institution.org"
                if re.fullmatch(rf'(?:{escaped_no_proxy})|(?:.+\.{escaped_no_proxy})', url_hostname):
                    bypass_proxy = True
                    break

            if not bypass_proxy:
                request.proxy_host = self.http_proxy_host
                request.proxy_port = self.http_proxy_port

        # pass call on to AsyncHTTPClient's configured implementation
        return self.client.fetch(request, raise_error)

    def close(self):
        return self.client.close()


def url_path_join(*pieces):
    """Join components of url into a relative url.

    Use to prevent double slash when joining subpath. This will leave the
    initial and final / in place.

    Copied from `notebook.utils.url_path_join`.
    """
    initial = pieces[0].startswith("/")
    final = pieces[-1].endswith("/")
    stripped = [s.strip("/") for s in pieces]
    result = "/".join(s for s in stripped if s)

    if initial:
        result = "/" + result
    if final:
        result = result + "/"
    if result == "//":
        result = "/"

    return result


# FIXME: remove when instantiating a kubernetes client
# doesn't create N-CPUs threads unconditionally.
# monkeypatch threadpool in kubernetes api_client
# to avoid instantiating ThreadPools.
# This is known to work for kubernetes-4.0
# and may need updating with later kubernetes clients

from unittest.mock import Mock
from kubernetes.client import api_client

_dummy_pool = Mock()
api_client.ThreadPool = lambda *args, **kwargs: _dummy_pool
