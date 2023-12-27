all:


wheel: clean
	CIBW_BUILD=cp38*x86_64 CIBW_BUILD_VERBOSITY=10 CIBW_SKIP="*musllinux*" cibuildwheel --platform linux

install:
	pip install -v .

clean:
	rm -rf dist/ wheel/ build/ *.whl wheelhouse/

cache-clean:
	rm -rf .py-build-cmake_cache/

get-dakota-src:
	rm -rf dakota
	git clone -j4 --branch v6.19.0 --depth 1 https://github.com/snl-dakota/dakota.git
	cd dakota && \
		git submodule update --init packages/external && \
		git submodule update --init packages/pecos && \
		git submodule update --init packages/surfpack
