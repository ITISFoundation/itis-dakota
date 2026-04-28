VENV := .venv
VENV_BIN := $(VENV)/bin
TEST_VENV := .venv-test
TEST_VENV_BIN := $(TEST_VENV)/bin

UV := $(shell command -v uv 2>/dev/null)

$(VENV):
ifdef UV
	uv venv $(VENV)
	uv pip install --python $(VENV_BIN)/python --upgrade pip cibuildwheel
else
	python3 -m venv $(VENV)
	$(VENV_BIN)/pip install --upgrade pip cibuildwheel
endif

all:

CCACHE_HOST_DIR := $(HOME)/.cache/itis-dakota-ccache

wheel: cache-clean clean $(VENV)
ifeq ($(shell uname -s),Darwin)
	@$(MAKE) --no-print-directory wheel-macos
else
	mkdir -p $(CCACHE_HOST_DIR)
	MAKEFLAGS="--no-print-directory" CIBW_BUILD="cp314-*" CIBW_ARCHS="$(shell uname -m)" CIBW_CONTAINER_ENGINE='docker; create_args: -v "$(CCACHE_HOST_DIR):/ccache"' CIBW_ENVIRONMENT='CMAKE_C_COMPILER_LAUNCHER=ccache CMAKE_CXX_COMPILER_LAUNCHER=ccache CCACHE_DIR=/ccache CCACHE_UMASK=000 BOOST_LIBRARYDIR=/usr/lib64/boost1.78 BOOST_INCLUDEDIR=/usr/include/boost1.78' $(VENV_BIN)/cibuildwheel --platform linux
endif

# Build a macOS wheel for the current host arch using cibuildwheel.
# Requires the Homebrew build deps to be installed once via `make brew-deps`.
# We set MACOSX_DEPLOYMENT_TARGET to the host's macOS major version so it
# matches the Homebrew bottles' minimum target (otherwise delocate refuses
# to bundle them).
wheel-macos: cache-clean clean $(VENV)
	MAC_MAJOR=$$(sw_vers -productVersion | cut -d. -f1).0; \
	PYVER=$$(python3 -c "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')"); \
	MAKEFLAGS="--no-print-directory" \
		MACOSX_DEPLOYMENT_TARGET=$$MAC_MAJOR \
		CIBW_BUILD="$$PYVER-*" \
		CIBW_ARCHS="$(shell uname -m)" \
		$(VENV_BIN)/cibuildwheel --platform macos

# One-time install of macOS build dependencies via Homebrew.
brew-deps:
	HOMEBREW_NO_INSTALL_UPGRADE=1 brew install --quiet boost hdf5 gsl lapack ccache cmake ninja gcc
	# Homebrew's gcc formula does NOT create an unversioned `gfortran`
	# symlink (only versioned ones like gfortran-15). Create one so
	# FC=$(brew --prefix)/bin/gfortran works for CMake's Fortran probe.
	ln -sf $$(ls $$(brew --prefix)/bin/gfortran-* | sort -V | tail -1) $$(brew --prefix)/bin/gfortran
	@echo "gfortran symlink:"
	@ls -la $$(brew --prefix)/bin/gfortran
	@$$(brew --prefix)/bin/gfortran --version

# Build wheel only if no wheel present in wheelhouse/
wheelhouse/.built:
	$(MAKE) wheel
	touch wheelhouse/.built

test: wheelhouse/.built
	rm -rf $(TEST_VENV)
	@WHEEL=$$(ls wheelhouse/itis_dakota-*.whl | head -1); \
	PYTAG=$$(echo $$WHEEL | sed -E 's/.*-(cp[0-9]+)-.*\.whl/\1/'); \
	PYVER=$$(echo $$PYTAG | sed -E 's/cp([0-9])([0-9]+)/\1.\2/'); \
	echo "Building test venv for Python $$PYVER (wheel: $$WHEEL)"; \
	if command -v uv >/dev/null 2>&1; then \
		uv venv --python $$PYVER $(TEST_VENV); \
		uv pip install --python $(TEST_VENV_BIN)/python pytest "$$WHEEL"; \
	else \
		python$$PYVER -m venv $(TEST_VENV); \
		$(TEST_VENV_BIN)/pip install pytest "$$WHEEL"; \
	fi
	. $(TEST_VENV_BIN)/activate && pytest

install: cache-clean
	pip install -v .

pipwheel: cache-clean clean
	MAKEFLAGS="--no-print-directory" pip wheel -v . -w wheel

clean:
	rm -rf dist/ wheel/ build/ *.whl wheelhouse/ $(TEST_VENV)

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

# Run the CI wheels-linux job locally via act (nektos/act).
# Usage:
#   make act-linux                           # default: cp313, native arch
#   make act-linux PYTHON=3.10 ARCH=x86_64   # override python / arch
ACT_PYTHON ?= 3.13
ACT_ARCH ?= $(shell uname -m | sed 's/x86_64/x86_64/;s/arm64/arm64/;s/aarch64/arm64/')
act-linux:
	mkdir -p .ccache wheelhouse
	rm -f wheelhouse/*.whl
	act -j wheels-linux \
		--matrix python:$(ACT_PYTHON) \
		--matrix arch:$(ACT_ARCH) \
		--container-architecture linux/$(ACT_ARCH) \
		--bind
