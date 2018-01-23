from binderhub.repoproviders import FakeProvider

c.BinderHub.use_registry = False
c.BinderHub.builder_required = False
c.BinderHub.repo_providers = {'gh': FakeProvider}
c.BinderHub.debug = True
c.BinderHub.enable_federation_portal =  True
c.BinderHub.port = 8585
c.BinderHub.federation_site_address = 'https://127.0.0.1:8585/'
c.BinderHub.default_binders = ['https://staging.mybinder.org', 'https://mybinder.org']
c.BinderHub.tornado_settings.update({'fake_build':True})
