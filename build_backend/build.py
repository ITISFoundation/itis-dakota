import subprocess
import sys

import py_build_cmake.build


def build_wheel(
    wheel_directory, config_settings=None, metadata_directory=None
):
    # Run setuptools_scm
    subprocess.run(
        [
            sys.executable,
            "-m",
            "setuptools_scm",
            "--force-write-version-files",
        ],
        check=True,
    )

    # Run the py_build_cmake build
    return py_build_cmake.build.build_wheel(
        wheel_directory, config_settings, metadata_directory
    )


def build_sdist(sdist_directory, config_settings=None):
    # Run setuptools_scm
    subprocess.run(
        [
            sys.executable,
            "-m",
            "setuptools_scm",
            "--force-write-version-files",
        ],
        check=True,
    )

    # Run the py_build_cmake build
    return py_build_cmake.build.build_sdist(sdist_directory, config_settings)
