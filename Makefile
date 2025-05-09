all:

wheel: cache-clean clean
	CIBW_BUILD="cp312-*" CIBW_ARCHS="x86_64" cibuildwheel --platform linux

test:
	python -m pytest

install: cache-clean
	pip install -v .

pipwheel: cache-clean clean
	pip wheel -v . -w wheel

clean:
	rm -rf dist/ wheel/ build/ *.whl wheelhouse/

cache-clean:
	rm -rf .py-build-cmake_cache/

get-dakota-src:
	rm -rf dakota
	git clone -j4 --branch v6.21.0 --depth 1 https://github.com/snl-dakota/dakota.git
	cd dakota && \
		git submodule update --init packages/external && \
		git submodule update --init packages/pecos && \
		git submodule update --init packages/surfpack && \
		git apply ../src_patches/findpython.patch && \
		git apply ../src_patches/pythoninclude.patch && \
		git apply ../src_patches/boost.patch && \
		git apply ../src_patches/dakenv_restart.patch && \
		git apply ../src_patches/cstdint_dak_types.patch && \
		git apply --whitespace=nowarn ../src_patches/adaptsampl_batch.patch
	cd dakota/packages/external && \
		git apply ../../../src_patches/cstdint.patch && \
		git apply ../../../src_patches/trilinos_cmake_version.patch
