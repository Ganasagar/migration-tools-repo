from dcos import http, config  # type: ignore
from typing import cast, Any, Dict, Optional
from urllib.parse import urlparse, ParseResult


class DCOSClient(object):
    """docstring for DCOSClient."""
    def __init__(self, toml_config: Optional[Any] = None):
        super(DCOSClient, self).__init__()
        self.toml_config = toml_config
        if toml_config is None:
            self.toml_config = config.get_config()

        self._dcos_url = cast(ParseResult, urlparse(config.get_config_val("core.dcos_url", toml_config)))

    @property
    def dcos_url(self) -> str:
        return self._dcos_url.geturl()

    def full_dcos_url(self, url_path: str) -> str:
        return "{dcos}/{url}".format(dcos=self.dcos_url, url=url_path)

    def request(self, method: str, url: str, **kwargs: Any) -> http.requests.Response:
        return http.request(method, url, toml_config=self.toml_config, **kwargs)

    def head(self, url: str, **kwargs: Any) -> http.requests.Response:
        return self.request("head", url, **kwargs)

    def get(self, url: str, **kwargs: Any) -> http.requests.Response:
        return self.request("get", url, **kwargs)

    def post(self,
             url: str,
             data: Optional[Any] = None,
             json: Optional[Dict[str, Any]] = None,
             **kwargs: Any) -> http.requests.Response:
        return self.request("post", url, data=data, json=json, **kwargs)

    def put(self, url: str, data: Optional[Any] = None, **kwargs: Any) -> http.requests.Response:
        return self.request('put', url, data=data, **kwargs)

    def patch(self, url: str, data: Optional[Any] = None, **kwargs: Any) -> http.requests.Response:
        return self.request('patch', url, data=data, **kwargs)

    def delete(self, url: str, data: Optional[Any] = None, **kwargs: Any) -> http.requests.Response:
        return self.request('delete', url, **kwargs)
