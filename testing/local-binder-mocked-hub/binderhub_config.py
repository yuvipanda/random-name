# A development config to test BinderHub's UI. The image building or the
# subsequent launching of the built image in a JupyterHub is mocked so that
# users get stuck forever waiting for a build to complete.

# Deployment assumptions:
# - BinderHub:  standalone local installation
# - JupyterHub: mocked

from binderhub.repoproviders import FakeProvider
from binderhub.build import FakeBuild

c.BinderHub.debug = True
c.BinderHub.use_registry = False
c.BinderHub.builder_required = False
c.BinderHub.repo_providers = {'gh': FakeProvider}
c.BinderHub.build_class = FakeBuild

c.BinderHub.about_message = "<blink>Hello world.</blink>"
c.BinderHub.banner_message = 'This is headline <a href="#">news.</a>'
