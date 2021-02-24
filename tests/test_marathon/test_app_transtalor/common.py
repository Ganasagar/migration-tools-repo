from dcos_migrate.plugins.marathon import app_secrets

class DummyAppSecretMapping(app_secrets.AppSecretMapping):
    def get_reference():
        raise NotImplementedError()

    def get_image_pull_secret_name():
        raise NotImplementedError()
