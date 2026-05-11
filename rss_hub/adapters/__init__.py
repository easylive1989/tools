from urllib.parse import urlparse

from . import hackmd


_ADAPTERS = {
    "hackmd.io": hackmd,
}


def get_adapter(url: str):
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    adapter = _ADAPTERS.get(host)
    if adapter is None:
        raise ValueError(f"No adapter registered for host: {host}")
    return adapter
