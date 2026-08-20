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

# When this checkout is a git worktree (e.g. `git worktree add`), .git is a
# file pointing at an absolute path under the main repo's .git/worktrees/...
# That path lives outside this project directory, so it isn't visible in the
# cibuildwheel container unless bind-mounted at the same absolute path too;
# without it, git/setuptools_scm can't resolve the repo and version detection
# fails with "no version found". Harmless no-op for a plain (non-worktree) clone.
GIT_COMMON_DIR := $(shell git rev-parse --path-format=absolute --git-common-dir)

wheel: cache-clean clean $(VENV)
ifeq ($(shell uname -s),Darwin)
	@$(MAKE) --no-print-directory wheel-macos
else
	mkdir -p $(CCACHE_HOST_DIR)
	MAKEFLAGS="--no-print-directory" CIBW_BUILD="cp314-*" CIBW_ARCHS="$(shell uname -m)" CIBW_CONTAINER_ENGINE='docker; create_args: -v "$(CCACHE_HOST_DIR):/ccache" -v "$(GIT_COMMON_DIR):$(GIT_COMMON_DIR)"' CIBW_ENVIRONMENT='CMAKE_C_COMPILER_LAUNCHER=ccache CMAKE_CXX_COMPILER_LAUNCHER=ccache CCACHE_DIR=/ccache CCACHE_UMASK=000 BOOST_LIBRARYDIR=/usr/lib64/boost1.78 BOOST_INCLUDEDIR=/usr/include/boost1.78' $(VENV_BIN)/cibuildwheel --platform linux
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
# uv is here (not before-all's pip install) since cibuildwheel resolves it relative to its own process, and only Homebrew's bin dir is on PATH for the whole job.
brew-deps:
	HOMEBREW_NO_INSTALL_UPGRADE=1 brew install --quiet boost hdf5 gsl lapack ccache cmake ninja gcc uv
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

DAKOTA_SRC_TARBALL_URL := https://github.com/snl-dakota/dakota/releases/download/v6.24.0/dakota-6.24.0-public-src-cli.tar.gz

# Use Sandia's official "public source" release tarball rather than git+submodules:
# it vendors packages/external, packages/pecos and packages/surfpack as flat
# source, pre-resolved to the versions actually shipped in the v6.24.0 release.
# The git submodule route is unreliable because the packages/surfpack commit
# pinned by the v6.24.0 tag is not reachable from the public GitHub mirror, forcing
# a substitution of an older surfpack revision that mismatches the NCSU DIRECT
# Fortran interface in packages/external (removed cdata/icsize args), causing a
# segfault in dirheader_() whenever a Kriging/EGO surrogate is built.
get-dakota-src:
	rm -rf dakota
	mkdir dakota
	# --exclude drops packages/external/eigen3's EIGEN3Config.cmake, a symlink
	# alias for Eigen3Config.cmake: harmless on case-sensitive filesystems, but
	# on macOS's case-insensitive one it collides with the real file and can
	# leave a dangling self-referential symlink in its place, breaking Dakota's
	# find_package(Eigen3) fallback.
	curl -sSL "$(DAKOTA_SRC_TARBALL_URL)" | tar xz --strip-components=1 --exclude='*/EIGEN3Config.cmake' -C dakota
	cd dakota && \
		for p in ../src_patches_v624/*.patch; do \
			patch -p1 --no-backup-if-mismatch < "$$p"; \
		done

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
