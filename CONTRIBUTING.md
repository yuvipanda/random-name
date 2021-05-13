# Contributing to BinderHub

Welcome! Thanks for spending time on developing BinderHub!
As a [Jupyter](https://jupyter.org) project, we follow the
[Jupyter contributor guide](https://jupyter.readthedocs.io/en/latest/contributing/content-contributor.html).

For all work on BinderHub you will need a copy of the source code.

[Fork](https://docs.github.com/en/github/getting-started-with-github/fork-a-repo) the BinderHub repository on [GitHub](https://github.com/jupyterhub/binderhub) and [clone](https://help.github.com/articles/cloning-a-repository/) it to your local computer.
   Then `cd` into it.

   ```bash
   git clone https://github.com/jupyterhub/binderhub
   cd binderhub
   ```

   Add a [remote](https://docs.github.com/en/github/collaborating-with-issues-and-pull-requests/configuring-a-remote-for-a-fork) and regularly [sync](https://docs.github.com/en/github/collaborating-with-issues-and-pull-requests/syncing-a-fork) to make sure you stay up-to-date with our repository:

   ```bash
   git remote add upstream https://github.com/jupyterhub/binderhub.git
   git checkout master
   git fetch upstream
   git merge upstream/master
   ```

There are several different setups for working on BinderHub.  Which setup is
best for you depends on which parts of BinderHub you want to change:

* the [documentation](#documentation-changes),
* the [user interface](#user-interface-changes),
* the [Python server](#python-server-changes), or
* the [helm chart](#helm-chart-changes).

Jump to the linked section for instructions on how to get setup.

This document also contains information on [common maintainer tasks](#common-maintainer-tasks).


## Documentation changes

Work on the documentation requires the least amount of setup. You will need
to have a modern version of [Python](https://www.python.org/). The documentation
uses the [reStructuredText markup language](http://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html).


1. Install BinderHub and the documentation tools:

   ```bash
   python3 -m pip install -r doc/doc-requirements.txt
   ```

1. The documentation is located in the `doc/` sub-directory, `cd` into it:

   ```bash
   cd ./doc
   ```

1. To build the documentation run:

   ```bash
   make html
   ```

1. Open the main documentation page in your browser, it is located at
   `_build/html/index.html`. On a Mac you can open it directly from the
   terminal with `open _build/html/index.html`.


## User interface changes

Work on the user interface requires a medium amount of setup. You will need
to have a modern version of [Python](https://www.python.org/) and
[npm](https://www.npmjs.com) installed.


1. Install BinderHub, the Python package.

   ```bash
   python3 -m pip install -e .
   ```

1. Install the NodeJS dependencies from package.json.

   ```bash
   npm install
   ```

1. Create the JS and CSS bundles BinderHub with:

   ```bash
   npm run webpack
   ```
   Note: you need to run this every time you make a change to the CSS or JS
   for them to take effect. Check out `npm run webpack:watch` to automate this.

1. Start the BinderHub webserver.

   ```bash
   python3 -m binderhub -f testing/local-binder-mocked-hub/binderhub_config.py
   ```

1. Visit http://localhost:8585 to see it in action.

Building and launching repositories will not work. You can still work on the
user interface of those parts as BinderHub is configured to fake those actions.
You can tell you are using the fake builder and launcher from the fact that the
build will never complete.

To learn how to set yourself up with a BinderHub development environment that lets
you modify the builder and launcher refer to the [Python server changes](#python-server-changes) section.


## Python server changes

Setting yourself up to make changes to the kubernetes integration of BinderHub
requires a few one-time setup steps. These steps are described in the
"One-time installation" section below. Follow those first then return here for
day to day development procedures.


### Day to day development tasks

After completing the "One-time installation" steps you are ready for day-to-day
development. These are the tasks you need to perform for every day development:

* Start and stop minikube with `minikube start` and `minikube stop`.
* Install JupyterHub in minikube with helm `./testing/local-binder-k8s-hub/install-jupyterhub-chart`
* Setup `docker` to use the same Docker daemon as your minikube cluster `eval $(minikube docker-env)`
* Start BinderHub `python3 -m binderhub -f testing/local-binder-k8s-hub/binderhub_config.py`
* Visit your BinderHub at http://localhost:8585

To test that everything works as it should visit http://localhost:8585/v2/gh/binder-examples/minimal-dockerfile/HEAD. This will build a very simple repository and should eventually
show you the classic Jupyter notebook interface.

To execute most of our test suite run: `pytest -svx -m "not auth"`

The tests should generate familiar pytest like output and complete in a few
minutes.

To run more advanced test or the full test suite we recommend you open a Pull Request
and let our Continuous Integration system run them. This is by far the easiest
way to find out if your changes pass all tests. Running these tests locally
is considered an expert task. To find out how to do it please read
`.github/workflows/test.yml` and replicate it for your local setup.

After working on BinderHub you can [clean up](#cleaning-up-resources).


### One-time installation

To run a full BinderHub it needs to have access to a kubernetes cluster
with a JupyterHub installed on it. This is what we will setup in this section.
All the steps are given as command-line commands for Ubuntu systems. They are
used as a common denominator that can be translated into the correct commands
on your local system.

Before you begin, there are a few utilities that need to be installed:
```bash
sudo apt install python3 python3-pip npm curl
```

If you are on linux, you may additionally need to install socat for port forwarding:

```bash
sudo apt install socat
```

1. [Install Minikube](https://minikube.sigs.k8s.io/docs/start/) to run Kubernetes locally.

  To start your minikube cluster , run the command: `minikube start`. This
  starts a local kubernetes cluster inside a virtual machine. This command
  assumes that you have already installed one of the VM drivers: virtualbox,
  xhyve or KVM2.

1. [Install helm](https://helm.sh/docs/intro/quickstart/#install-helm) to
   install JupyterHub and BinderHub on your cluster.

1. Add the JupyterHub helm charts repo:

  ```bash
  helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
  helm repo update
  ```

1. Install BinderHub the Python package and its development requirements:

   ```bash
   python3 -m pip install -e . -r dev-requirements.txt
   ```

1. Install JupyterHub in minikube with helm

  ```bash
  ./testing/local-binder-k8s-hub/install-jupyterhub-chart
  ```

1. Before starting your local deployment run:

  ```bash
  eval $(minikube docker-env)
  ```

  This command sets up `docker` to use the same Docker daemon as your minikube
  cluster does. This means images you build are directly available to the
  cluster. Note: when you no longer wish to use the minikube host, you can
  undo this change by running:

  ```bash
  eval $(minikube docker-env -u)
  ```

You are now setup for work on the Python server. Return to "day-to-day development tasks".


### Cleaning up resources

After you are done working on BinderHub you can clean up after yourself.

1. To cleanup the JupyterHub Helm chart you have installed in Kubernetes:

   ```bash
   helm delete binderhub-test
   ```

1. To stop running the Kubernetes cluster:

   ```bash
   minikube stop
   ```

1. Restore your docker daemon setup:

   ```bash
   eval $(minikube docker-env -u)
   ```


## Helm chart changes

This requires `helm` and a functional Kubernetes cluster. Please do
[preliminary Kubernetes setup](#one-time-installation) if you haven't already
before continuing here.

With a Kubernetes cluster running, as you verify with `kubectl version`, you can
continue.

1. Install development requirements, including `pytest` and `chartpress`.

   ```bash
   python3 -m pip install -r dev-requirements.txt
   ```

1. Configure `docker` using environment variables to use the same Docker daemon
   as your `minikube` cluster. This means images you build are directly
   available to the cluster.

   ```bash
   eval $(minikube docker-env)
   ```

1. Build the docker images referenced by the Helm chart and update its default
   values to reference these images.

   ```bash
   (cd helm-chart && chartpress)
   ```

1. Validate, and then install the Helm chart defined in helm-chart/binderhub.

   This validation step is not making any modification to your Kubernetes
   cluster, but will use it to validate if the Helm chart's rendered resources
   are valid Kubernetes resources according to the Kubernetes cluster.

   ```bash
   helm template --validate binderhub-test helm-chart/binderhub \
      --values testing/k8s-binder-k8s-hub/binderhub-chart-config.yaml \
      --set config.BinderHub.hub_url=http://$(minikube ip):30902 \
      --set config.BinderHub.access_token=$GITHUB_ACCESS_TOKEN
   ```

   If the validation succeeds, go ahead and upgrade/install the Helm chart.

   ```bash
   helm upgrade --install binderhub-test helm-chart/binderhub \
      --values testing/k8s-binder-k8s-hub/binderhub-chart-config.yaml \
      --set config.BinderHub.hub_url=http://$(minikube ip):30902 \
      --set config.BinderHub.access_token=$GITHUB_ACCESS_TOKEN

   echo "BinderHub inside the Minikube based Kubernetes cluster is starting up at http://$(minikube ip):30901"
   ```

1. Congratulations, you can now make changes and run the step above again to see
   how they influence the deployment. You can also start running `pytest` tests
   to verify the Deployment functions as it should.


## Tip: Use local repo2docker version

BinderHub runs repo2docker in a container. For testing the combination of an
unreleased repo2docker feature with BinderHub, you can use a locally built
repo2docker image. You can configure the image in the file
`testing/local-binder-k8s-hub/binderhub_config.py` with the following line:

```python
c.BinderHub.build_image = 'jupyter-repo2docker:my_image_tag'
```

**Important**: the image must be built using the same Docker daemon as the
minikube cluster, otherwise you get an error _"Failed to pull image [...]
repository does not exist or may require 'docker login'"_.

## Tip: Increase your GitHub API limit

By default, GitHub has a limit of 60 API requests per hour. We recommend
using a GitHub API token before running tests
in order to avoid hitting your API limit. Steps to do so are outlined in
the [BinderHub documentation](https://binderhub.readthedocs.io/en/latest/setup-binderhub.html#increase-your-github-api-limit).

## Tip: Start Minikube with more memory

By default, `minikube start` allocates 2GiB of main memory to the
underlying VM, which might be too low to run the builder successfully.

You may run `minikube start --memory 8192` to start Minikube with a 8GiB
VM underneath.


## Common maintainer tasks

These are tasks that BinderHub maintainers perform.

### Bumping the JupyterHub Helm chart version

The BinderHub Helm chart depends on the [JupyterHub Helm
chart](https://jupyterhub.github.io/helm-chart/), and its version is pinned
within `helm-chart/binderhub/requirements.yaml`.

To bump the version of JupyterHub that BinderHub uses, go to the [JupyterHub Helm Chart](https://jupyterhub.github.io/helm-chart/) version page, find the release
hash that you want and update the following field in the `requirements.yaml` file:

   ```yaml
   dependencies:
     version: "<helm-chart-version>"
   ```

**Make sure to double-check that there are no breaking changes in JupyterHub**.
Sometimes JupyterHub introduces breaking changes to its helm chart (such as the
structure of particular fields). Use the [JupyterHub Helm chart's
changelog](https://github.com/jupyterhub/zero-to-jupyterhub-k8s/blob/master/CHANGELOG.md)
to prepare for breaking changes associated with the version bump.


### Releasing

#### BinderHub Python package release checklist

* update/close the `CHANGES.md` for this release (see below)
* create a git tag for the release
* `pip install twine`
* `python setup.py sdist`
* `python setup.py bdist_wheel`
* `twine check dist/*` to check the README parses on PyPI
* edit `$HOME/.pypirc` to use the binder team account
* `twine upload dist/*`
* create a new release on https://github.com/jupyterhub/binderhub/releases
* add a new section at the top of the change log for future releases

For more details, see this [guide on uploading package to
PyPI](https://packaging.python.org/guides/distributing-packages-using-setuptools/#uploading-your-project-to-pypi).

#### Updating the changelog

As BinderHub does not have a typical semver release schedule, we try to
update the changelog in `CHANGES.md` every three months. A useful tool
for this [can be found here](https://github.com/choldgraf/github-activity).
If you choose to use this tool, the command that generated current sections
in the changelog is below:

```bash
github-activity jupyterhub/binderhub -s <START-DATE> -u <END-DATE> --tags enhancement,bug --strip-brackets
```

Copy and paste the output of this command into a new section in `CHANGES.md`.
