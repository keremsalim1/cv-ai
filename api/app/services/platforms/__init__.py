"""Per-portal overrides. Deliberately empty: an entry is added only when a
captured fixture shows the generic role-based rules failing on that portal.
Speculative entries are how this becomes four modules nobody can retire."""
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Platform:
    name: str
    hosts: tuple[str, ...]
    scope_landmark: str | None = None   # pin the scope generic rules get wrong


REGISTRY: tuple[Platform, ...] = ()


def platform_for(url: str) -> Platform | None:
    host = (urlparse(url).hostname or "").lower()
    for platform in REGISTRY:
        if any(host == h or host.endswith("." + h) for h in platform.hosts):
            return platform
    return None
