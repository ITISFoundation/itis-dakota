from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("itis-dakota")
except PackageNotFoundError:
    # package is not installed
    pass
