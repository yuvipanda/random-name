from binderhub.repoproviders import FakeProvider

c.BinderHub.use_registry = False
c.BinderHub.builder_required = False
c.BinderHub.debug = True
c.BinderHub.repo_providers = {'gh': FakeProvider}
c.BinderHub.tornado_settings.update({'fake_build':True})

c.BinderHub.about_message = "<blink>Hello world.</blink>"

c.BinderHub.banner_message = 'This is headline <a href="#">news.</a>'
