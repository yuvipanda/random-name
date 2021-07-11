from unittest import TestCase
from urllib.parse import quote

import pytest
from tornado.ioloop import IOLoop

from binderhub.repoproviders import (
    DataverseProvider,
    FigshareProvider,
    GistRepoProvider,
    GitHubRepoProvider,
    GitLabRepoProvider,
    GitRepoProvider,
    HydroshareProvider,
    SWHIDProvider,
    ZenodoProvider,
    strip_suffix,
    tokenize_spec,
)

sha1_validate = GitRepoProvider.sha1_validate


# General string processing
@pytest.mark.parametrize(
    'raw_text, suffix, clean_text', [
        ("foo.git", ".git", "foo"),
        ("foo.bar", ".git", "foo.bar"),
        ("foo.bar", ".bar", "foo")
    ]
)
def test_string_strip(raw_text, suffix, clean_text):
    assert strip_suffix(raw_text, suffix) == clean_text


# user/repo/reference
@pytest.mark.parametrize(
    'spec, raw_user, raw_repo, raw_ref', [
        ("user/repo/master", "user", "repo", "master"),
        ("user/repo/hotfix/squash-bug", "user", "repo", "hotfix/squash-bug"),
        ("user/repo/feature/save_world", "user", "repo", "feature/save_world")
    ]
)
def test_spec_processing(spec, raw_user, raw_repo, raw_ref):
    user, repo, unresolved_ref = tokenize_spec(spec)
    assert raw_user == user
    assert raw_repo == repo
    assert raw_ref == unresolved_ref


@pytest.mark.parametrize('spec,resolved_spec,resolved_ref,resolved_ref_url,build_slug', [
    ['10.5281/zenodo.3242074',
     '10.5281/zenodo.3242074',
     '3242074',
     'https://doi.org/10.5281/zenodo.3242074',
     'zenodo-3242074'],
    # 10.5281/zenodo.3242073 -> This DOI represents all versions, and will always resolve to the latest one
    # for now it is 3242074
    ['10.5281/zenodo.3242073',
     '10.5281/zenodo.3242074',
     '3242074',
     'https://doi.org/10.5281/zenodo.3242074',
     'zenodo-3242074'],
])
async def test_zenodo(spec, resolved_spec, resolved_ref, resolved_ref_url, build_slug):
    provider = ZenodoProvider(spec=spec)

    # have to resolve the ref first
    ref = await provider.get_resolved_ref()
    assert ref == resolved_ref

    slug = provider.get_build_slug()
    assert slug == build_slug
    repo_url = provider.get_repo_url()
    assert repo_url == spec
    ref_url = await provider.get_resolved_ref_url()
    assert ref_url == resolved_ref_url
    spec = await provider.get_resolved_spec()
    assert spec == resolved_spec


@pytest.mark.parametrize('spec,resolved_spec,resolved_ref,resolved_ref_url,build_slug', [
    ['10.6084/m9.figshare.9782777.v1',
     '10.6084/m9.figshare.9782777.v1',
     '9782777.v1',
     'https://doi.org/10.6084/m9.figshare.9782777.v1',
     'figshare-9782777.v1'],
    # spec without version is accepted as version 1 - check FigshareProvider.get_resolved_ref()
    ['10.6084/m9.figshare.9782777',
     '10.6084/m9.figshare.9782777.v1',
     '9782777.v1',
     'https://doi.org/10.6084/m9.figshare.9782777.v1',
     'figshare-9782777.v1'],
])
async def test_figshare(spec, resolved_spec, resolved_ref, resolved_ref_url, build_slug):
    provider = FigshareProvider(spec=spec)

    # have to resolve the ref first
    ref = await provider.get_resolved_ref()
    assert ref == resolved_ref

    slug = provider.get_build_slug()
    assert slug == build_slug
    repo_url = provider.get_repo_url()
    assert repo_url == spec
    ref_url = await provider.get_resolved_ref_url()
    assert ref_url == resolved_ref_url
    spec = await provider.get_resolved_spec()
    assert spec == resolved_spec


async def test_hydroshare():
    spec = 'https://www.hydroshare.org/resource/142c59757ed54de1816777828c9716e7'

    provider = HydroshareProvider(spec=spec)

    ref = await provider.get_resolved_ref()
    assert '142c59757ed54de1816777828c9716e7.v' in ref

    slug = provider.get_build_slug()
    assert 'hydroshare-142c59757ed54de1816777828c9716e7.v' in slug
    repo_url = provider.get_repo_url()
    assert repo_url == spec
    ref_url = await provider.get_resolved_ref_url()
    assert ref_url == repo_url
    resolved_spec = await provider.get_resolved_spec()
    assert resolved_spec == repo_url


async def test_hydroshare_doi():
    spec = '10.4211/hs.b8f6eae9d89241cf8b5904033460af61'

    provider = HydroshareProvider(spec=spec)

    ref = await provider.get_resolved_ref()
    assert 'b8f6eae9d89241cf8b5904033460af61.v' in ref

    slug = provider.get_build_slug()
    assert 'hydroshare-b8f6eae9d89241cf8b5904033460af61.v' in slug
    repo_url = provider.get_repo_url()
    assert repo_url == 'https://www.hydroshare.org/resource/b8f6eae9d89241cf8b5904033460af61'
    ref_url = await provider.get_resolved_ref_url()
    assert ref_url == repo_url
    resolved_spec = await provider.get_resolved_spec()
    assert resolved_spec == repo_url


@pytest.mark.parametrize('spec,resolved_spec,resolved_ref,resolved_ref_url,build_slug', [
    ['10.7910/DVN/TJCLKP',
     '10.7910/DVN/TJCLKP',
     '3035124.v3.0',
     'https://doi.org/10.7910/DVN/TJCLKP',
     'dataverse-dvn-2ftjclkp'],
    ['10.25346/S6/DE95RT',
     '10.25346/S6/DE95RT',
     '20460.v1.0',
     'https://doi.org/10.25346/S6/DE95RT',
     'dataverse-s6-2fde95rt']
])
async def test_dataverse(spec, resolved_spec, resolved_ref, resolved_ref_url, build_slug):
    provider = DataverseProvider(spec=spec)

    # have to resolve the ref first
    ref = await provider.get_resolved_ref()
    assert ref == resolved_ref

    slug = provider.get_build_slug()
    assert slug == build_slug
    repo_url = provider.get_repo_url()
    assert repo_url == spec
    ref_url = await provider.get_resolved_ref_url()
    assert ref_url == resolved_ref_url
    spec = await provider.get_resolved_spec()
    assert spec == resolved_spec


@pytest.mark.github_api
@pytest.mark.parametrize(
    "repo,unresolved_ref,resolved_ref",
    [
        (
            "jupyterhub/zero-to-jupyterhub-k8s",
            "f7f3ff6d1bf708bdc12e5f10e18b2a90a4795603",
            "f7f3ff6d1bf708bdc12e5f10e18b2a90a4795603",
        ),
        (
            "jupyterhub/zero-to-jupyterhub-k8s",
            "0.9.1",
            "38e50c71130fcf56655685f0992f4f125bef3879",
        ),
        ("jupyterhub/zero-to-jupyterhub-k8s", "HEAD", True),
        ("jupyterhub/zero-to-jupyterhub-k8s", "nosuchref", None),
    ],
)
def test_github_ref(repo, unresolved_ref, resolved_ref):
    spec = f"{repo}/{unresolved_ref}"
    provider = GitHubRepoProvider(spec=spec)
    slug = provider.get_build_slug()
    assert slug == repo.replace("/", "-")
    full_url = provider.get_repo_url()
    assert full_url == f"https://github.com/{repo}"
    ref = IOLoop().run_sync(provider.get_resolved_ref)
    if resolved_ref == True:
        # True means it should resolve, but don't check value
        assert ref is not None
        sha1_validate(ref)
    else:
        assert ref == resolved_ref
    if not resolved_ref:
        # we are done here if we don't expect to resolve
        return
    ref_url = IOLoop().run_sync(provider.get_resolved_ref_url)
    assert ref_url == f"https://github.com/{repo}/tree/{ref}"
    resolved_spec = IOLoop().run_sync(provider.get_resolved_spec)
    assert resolved_spec == f"{repo}/{ref}"


def test_not_banned():
    provider = GitHubRepoProvider(
        spec='jupyterhub/zero-to-jupyterhub-k8s/v0.4',
        banned_specs=[
            '^yuvipanda.*'
        ]
    )
    assert not provider.is_banned()


def test_banned():
    provider = GitHubRepoProvider(
        spec='jupyterhub/zero-to-jupyterhub-k8s/v0.4',
        banned_specs=[
            '^jupyterhub.*'
        ]
    )
    assert provider.is_banned()


def test_higher_quota():
    provider = GitHubRepoProvider(
        spec='jupyterhub/zero-to-jupyterhub-k8s/v0.4',
        high_quota_specs=[
            '^yuvipanda.*'
        ]
    )
    assert not provider.has_higher_quota()

def test_custom_config():
    base_config = {
        "pattern": '^jupyterhub.*',
        "config": {
            "key1": "val1",
            "quota": 999
        }
    }
    settings = {"per_repo_quota": 10}

    # If the spec matches nothing, we should just keep defaults
    provider = GitHubRepoProvider(
        spec='totallynotjupyterhub/zero-to-jupyterhub-k8s/v0.4',
        spec_config=[base_config]
    )
    assert provider.repo_config(settings)['quota'] == 10

    # Updating should happen w/ the base config
    provider = GitHubRepoProvider(
        spec='jupyterhub/zero-to-jupyterhub-k8s/v0.4',
        spec_config=[base_config]
    )
    assert provider.repo_config(settings)['key1'] == "val1"
    assert provider.repo_config(settings)['quota'] == 999

    # Not giving a string for the pattern should raise an error
    config_err_pattern = base_config.copy()
    config_err_pattern['pattern'] = 100
    provider = GitHubRepoProvider(
        spec='jupyterhub/zero-to-jupyterhub-k8s/v0.4',
        spec_config=[config_err_pattern]
    )
    with pytest.raises(ValueError):
        provider.repo_config(settings)

    # Not giving a dictionary for configuration should raise an error
    config_err_config = base_config.copy()
    config_err_config['config'] = "not a dictionary"
    provider = GitHubRepoProvider(
        spec='jupyterhub/zero-to-jupyterhub-k8s/v0.4',
        spec_config=[config_err_config]
    )
    with pytest.raises(ValueError):
        provider.repo_config(settings)

    # Not providing one of `pattern` or `config` should raise an error
    provider = GitHubRepoProvider(
        spec='jupyterhub/zero-to-jupyterhub-k8s/v0.4',
        spec_config=[base_config, {"pattern": "mypattern"}]
    )
    with pytest.raises(ValueError):
        provider.repo_config(settings)

    # Two regexes that both match should result in the *last* one being in the config
    base_config_second = {
        "pattern": '^jupyterh.*',
        "config": {
            "key1": "newvalue",
        }
    }
    provider = GitHubRepoProvider(
        spec='jupyterhub/zero-to-jupyterhub-k8s/v0.4',
        spec_config=[base_config, base_config_second]
    )
    assert provider.repo_config(settings)['key1'] == "newvalue"
    assert provider.repo_config(settings)['quota'] == 999



def test_not_higher_quota():
    provider = GitHubRepoProvider(
        spec='jupyterhub/zero-to-jupyterhub-k8s/v0.4',
        high_quota_specs=[
            '^jupyterhub.*'
        ]
    )
    assert provider.has_higher_quota()


@pytest.mark.parametrize('ban_spec', ['.*ddEEff.*', '.*ddEEFF.*'])
def test_ban_is_case_insensitive(ban_spec):
    provider = GitHubRepoProvider(
        spec='AABBCcc/DDeeFF/v0.4',
        banned_specs=[ban_spec]
    )
    assert provider.is_banned()


@pytest.mark.github_api
def test_github_missing_ref():
    provider = GitHubRepoProvider(spec='jupyterhub/zero-to-jupyterhub-k8s/v0.1.2.3.4.5.6')
    ref = IOLoop().run_sync(provider.get_resolved_ref)
    assert ref is None


class TestSpecErrorHandling(TestCase):

    def test_too_short_spec(self):
        spec = "nothing_to_split"
        with self.assertRaisesRegex(ValueError, "Spec is not of the form"):
            user, repo, unresolved_ref = tokenize_spec(spec)

    def test_long_spec(self):
        # No specification is too long, extra slashes go to the "ref" property
        spec = "a/long/specification/with/many/slashes/to/split/on"
        spec_parts = tokenize_spec(spec)
        assert len(spec_parts) == 3

    def test_spec_with_no_suggestion(self):
        spec = "short/master"
        error = "^((?!Did you mean).)*$".format(spec)  # negative match
        with self.assertRaisesRegex(ValueError, error):
            user, repo, unresolved_ref = tokenize_spec(spec)

    def test_spec_with_suggestion(self):
        spec = "short/suggestion"
        error = "Did you mean \"{}/master\"?".format(spec)
        with self.assertRaisesRegex(ValueError, error):
            user, repo, unresolved_ref = tokenize_spec(spec)


@pytest.mark.parametrize(
    "url,unresolved_ref,resolved_ref",
    [
        (
            "https://github.com/jupyterhub/zero-to-jupyterhub-k8s",
            "f7f3ff6d1bf708bdc12e5f10e18b2a90a4795603",
            "f7f3ff6d1bf708bdc12e5f10e18b2a90a4795603",
        ),
        (
            "https://github.com/jupyterhub/zero-to-jupyterhub-k8s",
            "0.8.0",
            "ada2170a2181ae1760d85eab74e5264d0c6bb67f",
        ),
        ("https://github.com/jupyterhub/zero-to-jupyterhub-k8s", "HEAD", True),
        ("https://github.com/jupyterhub/zero-to-jupyterhub-k8s", "nosuchref", None),
    ],
)
def test_git_ref(url, unresolved_ref, resolved_ref):
    spec = '{}/{}'.format(
        quote(url, safe=''),
        quote(unresolved_ref)
    )

    provider = GitRepoProvider(spec=spec)
    slug = provider.get_build_slug()
    assert slug == url
    full_url = provider.get_repo_url()
    assert full_url == url
    ref = IOLoop().run_sync(provider.get_resolved_ref)
    if resolved_ref == True:
        # True means it should resolve, but don't check value
        assert ref is not None
        sha1_validate(ref)
    else:
        assert ref == resolved_ref
    if not resolved_ref:
        # we are done here if we don't expect to resolve
        return
    ref_url = IOLoop().run_sync(provider.get_resolved_ref_url)
    assert ref_url == full_url
    resolved_spec = IOLoop().run_sync(provider.get_resolved_spec)
    assert resolved_spec == quote(url, safe="") + f"/{ref}"


@pytest.mark.parametrize(
    "unresolved_ref, resolved_ref",
    [
        ("v10.0.6", "b3344b7f17c335a817c5d7608c5e47fd7cabc023"),
        ("HEAD", True),
        ("nosuchref", None),
    ],
)
def test_gitlab_ref(unresolved_ref, resolved_ref):
    namespace = "gitlab-org/gitlab-foss"
    spec = "{}/{}".format(quote(namespace, safe=""), quote(unresolved_ref))
    provider = GitLabRepoProvider(spec=spec)
    slug = provider.get_build_slug()
    assert slug == 'gitlab_-org-gitlab_-foss'
    full_url = provider.get_repo_url()
    assert full_url == f'https://gitlab.com/{namespace}.git'
    ref = IOLoop().run_sync(provider.get_resolved_ref)
    if resolved_ref == True:
        # True means it should resolve, but don't check value
        assert ref is not None
        sha1_validate(ref)
    else:
        assert ref == resolved_ref
    if not resolved_ref:
        # we are done here if we don't expect to resolve
        return
    ref_url = IOLoop().run_sync(provider.get_resolved_ref_url)
    assert ref_url == f'https://gitlab.com/{namespace}/tree/{ref}'
    resolved_spec = IOLoop().run_sync(provider.get_resolved_spec)
    assert resolved_spec == quote(namespace, safe='') + f'/{ref}'


@pytest.mark.github_api
@pytest.mark.parametrize(
    "owner, gist_id, unresolved_ref, resolved_ref",
    [
        ("mariusvniekerk", "8a658f7f63b13768d1e75fa2464f5092", "", True),
        ("mariusvniekerk", "8a658f7f63b13768d1e75fa2464f5092", "HEAD", True),
        ("mariusvniekerk", "8a658f7f63b13768d1e75fa2464f5092", "master", True),
        (
            "mariusvniekerk",
            "8a658f7f63b13768d1e75fa2464f5092",
            "7daa381aae8409bfe28193e2ed8f767c26371237",
            "7daa381aae8409bfe28193e2ed8f767c26371237",
        ),
        ("mariusvniekerk", "8a658f7f63b13768d1e75fa2464f5092", "nosuchref", None),
    ],
)
def test_gist_ref(owner, gist_id, unresolved_ref, resolved_ref):
    spec = f"{owner}/{gist_id}/{unresolved_ref}"

    provider = GistRepoProvider(spec=spec)
    slug = provider.get_build_slug()
    assert slug == gist_id
    full_url = provider.get_repo_url()
    assert full_url == f"https://gist.github.com/{owner}/{gist_id}.git"
    ref = IOLoop().run_sync(provider.get_resolved_ref)
    if resolved_ref == True:
        # True means it should resolve, but don't check value
        assert ref is not None
        sha1_validate(ref)
    else:
        assert ref == resolved_ref
    if not resolved_ref:
        # we are done here if we don't expect to resolve
        return
    ref_url = IOLoop().run_sync(provider.get_resolved_ref_url)
    assert ref_url == f"https://gist.github.com/{owner}/{gist_id}/{ref}"
    resolved_spec = IOLoop().run_sync(provider.get_resolved_spec)
    assert resolved_spec == f"{owner}/{gist_id}/{ref}"


@pytest.mark.github_api
def test_gist_secret():
    spec = '{}/{}'.format('mariusvniekerk', 'bd01411ea4bf4eb8135893ef237398ba')

    provider = GistRepoProvider(spec=spec)
    with pytest.raises(ValueError):
        IOLoop().run_sync(provider.get_resolved_ref)

    provider = GistRepoProvider(spec=spec, allow_secret_gist=True)
    assert IOLoop().run_sync(provider.get_resolved_ref) is not None


@pytest.mark.parametrize('spec,resolved_spec,resolved_ref,resolved_ref_url,build_slug', [
    ['swh:1:rev:c30614ec4587418fb264efb466cba58991029f16',
     'swh:1:rev:c30614ec4587418fb264efb466cba58991029f16',
     'swh:1:rev:c30614ec4587418fb264efb466cba58991029f16',
     'swh:1:rev:c30614ec4587418fb264efb466cba58991029f16',
     'swh-swh:1:rev:c30614ec4587418fb264efb466cba58991029f16'],
])
async def test_swh(spec, resolved_spec, resolved_ref, resolved_ref_url, build_slug):
    provider = SWHIDProvider(spec=spec)

    # have to resolve the ref first
    ref = await provider.get_resolved_ref()
    assert ref == resolved_ref

    slug = provider.get_build_slug()
    assert slug == build_slug
    repo_url = provider.get_repo_url()
    assert repo_url == spec
    ref_url = await provider.get_resolved_ref_url()
    assert ref_url == resolved_ref_url
    spec = await provider.get_resolved_spec()
    assert spec == resolved_spec
