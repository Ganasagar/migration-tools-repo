import json
from typing import Any, Dict


class AdditionalFlagNeeded(Exception):
    """
    Raised to indicate that for this specific case of migration the user is obliged
    to specify a flag which could otherwise have been omitted.
    """
    pass


class InvalidAppDefinition(Exception):
    pass


def pod_spec_update(fields: Dict[str, Any]) -> Dict[str, Any]:
    return {'spec': {'template': {'spec': fields}}}


def main_container(fields: Dict[str, Any]) -> Dict[str, Any]:
    # NOTE: All updates for the main container set the same "name" field.
    assert 'name' not in fields
    _fields = {'name': 'main'}
    _fields.update(fields)

    return pod_spec_update({'containers': [_fields]})


def try_oneline_dump(obj: Any) -> str:
    dump = json.dumps(obj)
    return dump if len(dump) <= 78 else json.dumps(obj, indent=2)
