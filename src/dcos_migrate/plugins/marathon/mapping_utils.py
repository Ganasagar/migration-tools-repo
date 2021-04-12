"""
This module contains utilites for mapping an object serialized from JSON
with semi-independent fields into another JSON-serializable object.
"""

from collections import namedtuple
from typing import (cast, Any, Callable, Dict, Iterator, List, Mapping, Optional, Tuple, TypeVar, Set, Union)


class Translated(object):
    """
        A return value of mapper functions passed into `apply_mapping()`
    """
    def __init__(self, update: Optional[Dict[str, Any]] = None, warnings: Optional[List[str]] = None):
        self.update: Dict[str, Any] = {} if update is None else update
        self.warnings: List[str] = [] if warnings is None else warnings

    def merged_with(self, other: 'Translated') -> 'Translated':
        return Translated(update=deep_merge(self.update, other.update), warnings=self.warnings + other.warnings)


MappingKey = Union[str, Tuple[str, ...]]


def apply_mapping(mapping: Mapping[MappingKey, Callable[[Any], Translated]], data: Mapping[str, Any],
                  error_location: str) -> Tuple[Dict[str, Any], List[str]]:
    """
    >>> mapper = lambda n: Translated({"outer": [{"inner": n*2}]})
    >>> result, _ = apply_mapping({"foo": mapper}, {"foo": 21}, "")
    >>> result == {"outer": [{"inner": 42}]}
    True

    >>> mapper = lambda d: Translated({"product": d['foo'] * d['bar']})
    >>> result, _ = apply_mapping({("foo", "bar"): mapper}, {"foo": 21, "bar": 2}, "")
    >>> result == {"product": 42}
    True

    >>> mapper = lambda n: Translated({"result": n})
    >>> apply_mapping({"foo": mapper}, {"foo": 1, "bar": 2, "baz": 0}, "app")
    Traceback (most recent call last):
        ...
    RuntimeError: "app" has fields "bar", "baz" that are not present in the field mappings

    >>> mapper = lambda n: Translated({"result": n})
    >>> apply_mapping({"foo": mapper, "bar": mapper}, {"foo": 1, "bar": 2}, "app")
    Traceback (most recent call last):
        ...
    Exception: Error composing the result object for "app": Conflicting values for .result: 2 and 1

    >>> broken_mapper = lambda n: str(n)
    >>> apply_mapping({"foo": broken_mapper}, {"foo": 1}, "app")
    Traceback (most recent call last):
        ...
    Exception: Bad translation result in "app" for key "foo"

    """
    def map_group(group: MappingKey, mapper: Callable[[Any], Translated]) -> Tuple[Set[str], Translated]:
        if isinstance(group, tuple):
            fields = set(group) & data.keys()
            return fields, mapper({field: data[field] for field in fields})

        try:
            value = data[group]
        except KeyError:
            return set(), Translated()

        return {group}, mapper(value)

    unknown = data.keys()
    result: Dict[Any, Any] = {}
    warnings = []

    for key in sorted(mapping.keys(), key=str):
        mapper = mapping[key]
        mapped_app_fields, translated = map_group(key, mapper)
        if not isinstance(translated, Translated):
            raise Exception('Bad translation result in "{}" for key "{}"'.format(error_location, key))

        warnings += ['"{}": {}'.format(key, warn) for warn in translated.warnings]

        try:
            result = deep_merge(result, translated.update)
        except UpdateConflict as err:
            raise Exception('Error composing the result object for "{}": {}'.format(error_location, err))

        unknown -= mapped_app_fields

    if unknown:
        # We intentionally crash the script when unknown fields are discovered.
        # The fields that cannot or should not be mapped should be explicitly added
        # into the corresponding `generate_..._mappings()` function.
        raise RuntimeError('"{}" has fields {} that are not present in the field mappings'.format(
            error_location, ', '.join('"{}"'.format(_) for _ in sorted(unknown))))

    return result, warnings


# This is used in objects passed into `deep_merge()` to apply an alternative
# way of merging lists: the list on the left is extended with items from
# the ListExtension on the right.
ListExtension = namedtuple('ListExtension', ['items'])


class UpdateConflict(Exception):
    pass


T = TypeVar('T')


def deep_merge(first: T, second: T, debug_prefix: str = '') -> T:
    """
    >>> result = deep_merge({5: 6, 3: {"bar": "baz"}}, {1: 2, 3: {"foo": "bar"}})
    >>> result == {1: 2, 3: {"foo": "bar", "bar": "baz"}, 5: 6}
    True

    >>> result = deep_merge({1: 2, 3: {"foo": "bar"}}, {5: 6, 3: {"bar": "baz"}})
    >>> result == {1: 2, 3: {"foo": "bar", "bar": "baz"}, 5: 6}
    True

    >>> result = deep_merge({3: [{"foo": "bar"}]}, {3: [{"bar": "baz"}, "deadbeef"]})
    >>> result == {3: [{"foo": "bar", "bar": "baz"}, "deadbeef"]}
    True

    >>> result = deep_merge({3: [{"bar": "baz"}, "deadbeef"]}, {3: [{"foo": "bar"}]})
    >>> result == {3: [{"foo": "bar", "bar": "baz"}, "deadbeef"]}
    True

    >>> deep_merge({"foo": 1}, {"foo": 1}) == {"foo": 1}
    True

    >>> deep_merge({"foo": 1}, {"foo": 2}) # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UpdateConflict: Conflicting values for .foo: 1 and 2

    >>> deep_merge([1], ListExtension([2]))
    [1, 2]

    >>> deep_merge(ListExtension([1, 2]), [3])
    [3, 1, 2]

    >>> result = deep_merge(ListExtension([1]), ListExtension([2]))
    >>> result == ListExtension([1, 2])
    True

    >>> result = deep_merge({"foo": [1]}, {"foo": ListExtension([2])})
    >>> result == {"foo": [1, 2]}
    True

    >>> result = deep_merge({"foo": ListExtension([1])}, {"bar": [2]})
    >>> result == {"foo": ListExtension([1]), "bar": [2]}
    True
    """
    if all(isinstance(_, dict) for _ in (first, second)):

        def iter_items(first: Dict[str, Any], second: Dict[str, Any]) -> Iterator[Tuple[str, Any]]:
            for key in first.keys() - second.keys():
                yield key, first[key]
            for key in second.keys() - first.keys():
                yield key, second[key]
            for key in first.keys() & second.keys():
                yield key, deep_merge(first[key], second[key], debug_prefix + '.' + str(key))

        return cast(T, dict(iter_items(cast(Dict[str, Any], first), cast(Dict[str, Any], second))))

    if isinstance(first, List) and isinstance(second, List):
        min_len = min(len(first), len(second))
        return cast(T, [deep_merge(first[n], second[n], '{}[{}]'.format(debug_prefix, n))
                        for n in range(min_len)] + first[min_len:] + second[min_len:])

    if any(isinstance(_, ListExtension) for _ in (first, second)):
        base, extension = (first, second) if isinstance(second, ListExtension) else (second, first)
        assert isinstance(extension, ListExtension)
        if isinstance(base, ListExtension):
            return cast(T, ListExtension(base.items + extension.items))
        if isinstance(base, list):
            return cast(T, base + extension.items)

    if first == second:
        return first

    raise UpdateConflict('Conflicting values for {}: {} and {}'.format(debug_prefix, first, second))


def finalize_unmerged_list_extensions(merged: Any) -> Any:
    if isinstance(merged, ListExtension):
        merged = merged.items

    if isinstance(merged, list):
        return [finalize_unmerged_list_extensions(item) for item in merged]

    if isinstance(merged, dict):
        return {key: finalize_unmerged_list_extensions(value) for key, value in merged.items()}

    return merged
