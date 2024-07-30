from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("osparc_filecomms")
except PackageNotFoundError:
    # package is not installed
    pass
