## Run Tests:
# pytest --doctest-modules

from functools import reduce
import json
from copy import copy


def deep_merge(dest, src):
    """
    >>> a = { 'b': [{'d': 1}, 2] }
    >>> b = { 'b': [{'c': 1}] }
    >>> deep_merge(b, a)
    {'b': [{'c': 1, 'd': 1}, 2]}

    >>> deep_merge(a, b)
    {'b': [{'d': 1, 'c': 1}, 2]}
    """
    if isinstance(dest, list) and isinstance(src, list):
        # if src is longer than dest, we need to extend dest to fit those elements
        result = copy(dest) + ([None] * (len(src) - len(dest)))
        for i in range(max(len(src), len(dest))):
            result[i] = dest[i] if len(src) <= i else deep_merge(result[i], src[i])
        return result

    if isinstance(dest, dict) and isinstance(src, dict):
        result = copy(dest)
        for k, v in src.items():
            result[k] = deep_merge(dest.get(k), src[k])
        return result
    # if we're not merging dicts or lists, src wins!
    return src


def flatten(value, prefix=""):
    """
    >>> flatten({'a': {'b': 1, 'c': [2, 3]}})
    {'.a.b': 1, '.a.c.0': 2, '.a.c.1': 3}

    We want to do something like that to ensure that we handled all props that
    occurred in the given spec.
    """

    def merge_via(xs, prefix):
        d = {}
        for k, v in xs:
            d.update(flatten(v, f"{prefix}.{k}"))
        return d

    if isinstance(value, dict):
        return merge_via(value.items(), prefix)

    if isinstance(value, list):
        return merge_via(enumerate(value), prefix)

    return {prefix: value}
