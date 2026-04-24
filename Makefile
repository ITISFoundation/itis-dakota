VENV := .venv
VENV_BIN := $(VENV)/bin

$(VENV):
	python3 -m venv $(VENV)
	$(VENV_BIN)/pip install --upgrade pip cibuildwheel

all:

CCACHE_HOST_DIR := $(HOME)/.cache/itis-dakota-ccache

wheel: cache-clean clean $(VENV)
	mkdir -p $(CCACHE_HOST_DIR)
	MAKEFLAGS="--no-print-directory" CIBW_BUILD="cp314-*" CIBW_ARCHS="$(shell uname -m)" CIBW_CONTAINER_ENGINE='docker; create_args: -v "$(CCACHE_HOST_DIR):/ccache"' CIBW_ENVIRONMENT='CMAKE_C_COMPILER_LAUNCHER=ccache CMAKE_CXX_COMPILER_LAUNCHER=ccache CCACHE_DIR=/ccache CCACHE_UMASK=000 BOOST_LIBRARYDIR=/usr/lib64/boost1.78 BOOST_INCLUDEDIR=/usr/include/boost1.78' $(VENV_BIN)/cibuildwheel --platform linux

test:
	python -m pytest

install: cache-clean
	pip install -v .

pipwheel: cache-clean clean
	MAKEFLAGS="--no-print-directory" pip wheel -v . -w wheel

clean:
	rm -rf dist/ wheel/ build/ *.whl wheelhouse/

cache-clean:
	rm -rf .py-build-cmake_cache/

get-dakota-src:
	rm -rf dakota
	git clone -j4 --branch v6.23.0 --depth 1 https://github.com/snl-dakota/dakota.git
	cd dakota && \
		git submodule update --init packages/external && \
		git submodule update --init packages/pecos && \
		git submodule update --init packages/surfpack && \
		git apply --whitespace=nowarn ../src_patches_v623/*.patch
