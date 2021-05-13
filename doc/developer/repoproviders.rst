.. _providers-section:

====================
Repository Providers
====================

Repository Providers (or RepoProviders) are
locations where repositories are stored (e.g.,
GitHub). BinderHub supports a number of providers out of the
box, and can be extended to support new providers. For a complete
listing of the provider classes, see :ref:`api-repoproviders`.

Supported repoproviders
=======================

Currently supported providers, their prefixes and specs are:

.. table::
    :widths: 5 5 55 35

    +------------+--------------------+-------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------+
    | Provider   | provider_prefix    | spec                                                        | notes                                                                                                                                     |
    +============+====================+=============================================================+===========================================================================================================================================+
    | GitHub     | ``gh``             | ``<user>/<repo>/<commit-sha-or-tag-or-branch>``             | `GitHub <https://github.com/>`_ is a website for hosting and sharing git repositories.                                                    |
    +------------+--------------------+-------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------+
    | GitLab     | ``gl``             | ``<url-escaped-namespace>/<unresolved_ref>``                | `GitLab <https://about.gitlab.com/>`_ offers hosted as well as self-hosted git repositories.                                              |
    |            |                    | (e.g. ``group%2Fproject%2Frepo/master``)                    |                                                                                                                                           |
    +------------+--------------------+-------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------+
    | Gist       | ``gist``           | ``<github-username>/<gist-id><commit-sha-or-tag>``          | `Gists <https://gist.github.com/>`_ are small collections of files stored on GitHub. They behave like lightweight repositories.           |
    +------------+--------------------+-------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------+
    | Zenodo     | ``zenodo``         | ``<zenodo-DOI>``                                            | `Zenodo <https://zenodo.org/>`_ is a non-profit provider of scholarly artifacts (such as code repositories) run in partnership with CERN. |
    +------------+--------------------+-------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------+
    | Figshare   | ``figshare``       | ``<figshare-DOI>``                                          | `FigShare <https://figshare.com/>`_ is a company that offers hosting for scholarly artifacts (such as code repositories).                 |
    +------------+--------------------+-------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------+
    | HydroShare | ``hydroshare``     | ``<hydroshare-DOI-or-ResourceID>``                          | `HydroShare <https://www.hydroshare.org/>`_ is a hydrologic information system for users to share and publish data and models.            |
    +------------+--------------------+-------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------+
    | Dataverse  | ``dataverse``      | ``<dataverse-DOI>``                                         | `Dataverse <https://dataverse.org/>`_ is open source research data repository software installed all over the world.                      |
    +------------+--------------------+-------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------+
    | Git        | ``git``            | ``<url-escaped-url>/<commit-sha>``                          | A generic repository provider for URLs that point directly to a git repository.                                                           |
    +------------+--------------------+-------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------+

Adding a new repository provider
================================

It is possible to add new repository providers to BinderHub, allowing
a BinderHub deployment to fetch repositories from new locations
on the web. Doing so involves defining your own RepoProvider sub-class
and modifying a set of methods/attributes to interface with the online
provider to which you are providing access. It also often involves
`building a new repo2docker content provider <https://github.com/jupyter/repo2docker/tree/master/repo2docker/contentproviders>`_.

In order to extend the supported repository providers,
follow these instructions. We'll provide example links for each step to a
recent `BinderHub pull-request <https://github.com/jupyterhub/binderhub/pull/969>`_
that implements the ``DataverseProvider`` class.

#. Review the `repoprovider module <https://github.com/jupyterhub/binderhub/blob/master/binderhub/repoproviders.py>`_.
   This shows a number of example repository providers.
#. Check whether repo2docker has a `ContentProvider class <https://github.com/jupyter/repo2docker/tree/master/repo2docker/contentproviders>`_
   that will work with your repository provider. If not, then you'll need to create one first.
#. Create a new class that sub-classes the ``RepoProvider`` class.
   Define your own methods for actions that are repository provider-specific.
   For example, `here is the DataverseProvider class <https://github.com/jupyterhub/binderhub/pull/969/files#diff-c5688934f1e6dc3e932b6c84c1bbbd5dR298>`_.
#. Add this class to the `list of default RepoProviders in BinderHub <https://github.com/jupyterhub/binderhub/pull/969/files#diff-a15f2374919ff29de22fa29a192b1fd1R397>`_.
#. Add the new provider prefix `to the BinderHub UI <https://github.com/jupyterhub/binderhub/pull/969/files#diff-29b962b0b049b65a0fed0d8b5dc838b9R58>`_
   and `the index javascript <https://github.com/jupyterhub/binderhub/pull/969/files#diff-d46aa1f6b1ea4f726708fcc1cd34e994R92>`_
   and make the appropriate changes to the index page based on the URL
   specification for this repository provider.
#. Add `a test for your repoprovider <https://github.com/jupyterhub/binderhub/pull/969/files#diff-360740f27b99f96e330327e34440a0e8R102>`_
   to ensure that it properly resolves and fetches a repository URL.
#. Document your new repository provider on the :ref:`providers-section` page as well
   as the :ref:`api-repoproviders` page.
