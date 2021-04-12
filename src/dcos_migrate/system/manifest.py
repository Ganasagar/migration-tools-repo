import yaml
import logging
import inspect
import itertools

from typing import Any, Iterable, List, Optional, Type

from kubernetes.client import ApiClient  # type: ignore
import kubernetes.client.models  # type: ignore


def with_comment(object_cls: Type[object]) -> Type[object]:
    """
    This can be used as a class decorator:
    @with_comment
    class V1ServiceWithComment(V1Service):
        pass

    def create_service():
        return V1ServiceWithComment().set_comment(['This is an empty service']))

    def print_comment(service:V1ServiceWithComment):
        print('\n'.join(service.get_comment()))
    """
    for method in ('set_comment', 'get_comment'):
        if any(k == method for k, _ in inspect.getmembers(object_cls)):
            raise Exception("{} already defines '{}'".format(object_cls.__name__, method))

    class ObjectWithComment(object_cls  # type: ignore # https://github.com/python/mypy/issues/5865
                            ):
        def set_comment(self, comment: Iterable[str]) -> None:
            self.__comment = comment

        def get_comment(self) -> Iterable[str]:
            try:
                return self.__comment
            except AttributeError:
                return []

    return ObjectWithComment


def _extract_comment(obj: Any) -> str:
    try:
        get_comment = obj.get_comment
    except AttributeError:
        return ""

    pieces = get_comment()
    lines_iter = itertools.chain.from_iterable(p.splitlines() for p in pieces)
    return ''.join('# {}\n'.format(line) for line in lines_iter)


class Manifest(List[Any]):
    """docstring for Manifest."""
    def __init__(self, pluginName: str, manifestName: str = "", data: List[Any] = [], extension: str = 'yaml'):
        super(Manifest, self).__init__(data)
        self._plugin_name = pluginName
        self._name = manifestName
        self._extension = extension
        self._serializer = self.dumps
        self._deserializer = yaml.safe_load_all

        self.resources = []  # type: ignore

    def dumps(self, data: Any) -> str:
        docs = []
        for d in self:
            kc = ApiClient()
            doc = kc.sanitize_for_serialization(d)
            orderedDoc = {}
            # specify the key order: a,k,m,s/d
            for k in ['apiVersion', 'kind', 'metadata', 'type', 'spec', 'data', 'stringData']:
                if k in doc.keys():
                    orderedDoc[k] = doc[k]

            document = _extract_comment(d) + yaml.dump(orderedDoc, sort_keys=False)
            logging.debug("Found doc: {}".format(document))
            docs.append(document)

        return "---\n" + '\n---\n'.join(docs)

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, val: str) -> None:
        self._name = val

    @property
    def plugin_name(self) -> str:
        return self._plugin_name

    @property
    def extension(self) -> str:
        return self._extension

    def resource_by_name(self, name: str, apiVersion: str, kind: str) -> Optional[Any]:
        for r in self.resources:
            if r.Name == name and r.apiVersion == apiVersion and r.kind == kind:
                return r
        return None

    def resource_idx_by_name(self, name: str, apiVersion: str, kind: str) -> Optional[int]:
        for i in range(len(self.resources)):
            r = self.resources[i]
            if r.Name == name and r.apiVersion == apiVersion and r.kind == kind:
                return i
        return None

    def serialize(self) -> str:
        return self._serializer(self)

    def deserialize(self, data: str) -> None:
        dload = self._deserializer(data)
        for dsi in dload:
            ds = dict(dsi)
            if ds is None:
                logging.warning("serialized object is none of data: {}".format(data))
                continue

            if 'apiVersion' in ds and 'kind' in ds:
                model = self.getModel(ds['kind'], ds['apiVersion'])
                if model:
                    kc = ApiClient()
                    di = kc._ApiClient__deserialize(ds, model)
                    self.append(di)
                continue
            else:
                logging.warning("Missing apiVersion and/or kind in data: {}".format(ds))

            self.append(ds)

    @classmethod
    def genModelName(self, apiVersion: str, kind: str) -> str:
        apiv = apiVersion.split("/")[-1]
        return "{}{}".format(apiv[0].upper() + apiv[1:], kind)

    @classmethod
    def getModel(self, kind: str, apiVersion: str) -> Optional[Any]:
        for cls in inspect.getmembers(kubernetes.client.models, inspect.isclass):
            if cls[0] == self.genModelName(apiVersion, kind):
                return cls[1]
        return None

    def findall_by_annotation(self, annotation: str, value: Optional[str] = None) -> Optional[List[str]]:
        rs = []
        for r in self.resources:
            for a, v in r.metadata.annotations.items():
                if a == annotation:
                    if value is None:
                        rs.append(r)
                    else:
                        if v == value:
                            rs.append(r)

        if len(rs) > 0:
            return rs
        return None

    def find_by_annotation(self, annotation: str, value: Optional[str] = None) -> Optional[str]:
        r = self.findall_by_annotation(annotation=annotation, value=value)
        if r is None:
            return r

        # return first match
        return r[0]
