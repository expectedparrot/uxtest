"""uxtest: file-based synthetic-user UX studies."""

from importlib.metadata import PackageNotFoundError, version

from .store import Store, StoreError, find_store

try:
    __version__ = version("uxtest")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["Store", "StoreError", "find_store", "__version__"]
