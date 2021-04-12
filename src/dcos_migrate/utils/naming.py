import re
from typing import List

DCOS_MIGRATE_NAMESPACE = "migration.dcos.d2iq.com"

_invalid_label = re.compile('[^-a-zA-Z0-9]')


def make_label(name: str) -> str:
    # An alphanumeric (a-z, and 0-9) string, with a maximum length of 63
    # characters, with the '-' character allowed anywhere except the first or
    # last character, suitable for use as a hostname or segment in a domain
    # name.

    if not name:
        name = 'x'
    # Recode the name as ASCII, ignoring any non-ascii characters
    name = name.encode().decode('ascii', errors='ignore')
    # Replace any non-alphanumeric values with `-`
    name = _invalid_label.sub('-', name)
    # Name cannot be longer than 63 characters
    name = name[:63]
    # First and last character cannot be `-`
    if name[0] == '-':
        name = 'x' + name[1:]
    if name[-1] == '-':
        name = name[:-1] + '0'
    return name


# Labels can have upper and lower case, and if the name is > 63 characters we have no choice but to truncate.
# Subdomains are labels but must be lowercase and we can fit longer names into multiple segments.
# Hence `make_segment` is similar to `make_label` without lowercasing and using dots to keep more data.
def make_segment(name: str) -> str:
    parts = []
    names = name.split('.')
    for name in names:
        if not name:
            name = 'x'
        # Recode the name as ASCII, ignoring any non-ascii characters
        name = name.encode().decode('ascii', errors='ignore')
        # Replace any non-alphanumeric values with `-`
        name = _invalid_label.sub('-', name)
        while name:
            # First character must be alphabetic
            if not name[0].isalpha():
                name = 'x' + name
            part = name[:63]
            name = name[63:]
            if part[-1] == '-':
                part = part[:62] + '0'
            parts.append(part)
    return '.'.join(parts)


def make_subdomain(names: List[str]) -> str:
    # One or more lowercase rfc1035/rfc1123 labels separated by '.' with a
    # maximum length of 253 characters.

    # `filter` removes any empty names
    # `make_segment` breaks names into valid name segments
    name = ".".join([make_segment(n) for n in filter(None, names)])

    # Truncate to maximum size. If this puts a dot or dash at the end, then
    # keep truncating.
    name = name[:253]
    while name and name[-1] in '.-':
        name = name[:-1]

    return name.lower()


def dnsify(name: str) -> str:
    """
    Replace DC/OS folders with dots and
    replace other invalid characters with `_`

    >>> dnsify("folder/sec!ret")
    "folder.sec_ret"
    """
    _invalid_secret_key = re.compile('[^-._a-zA-Z0-9]')
    # Replace DC/OS folders with dots
    name = ".".join(list(filter(None, name.split("/"))))
    # Replace other invalid characters with `_`
    # `folder/sec!ret` becomes `folder.sec_ret`
    return _invalid_secret_key.sub('_', name)


def namespace_path(name: str) -> str:
    """
    Uses namespace constant. Adds every argument as path part

    >>> namespace_path("cluster-id")
    "migration.dcos.d2iq.com/cluster-id"
    """
    return "/".join([DCOS_MIGRATE_NAMESPACE, name])
