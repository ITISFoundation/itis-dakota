all:


wheel: cache-clean clean
	CIBW_BUILD=cp38*x86_64 cibuildwheel --platform linux

install:
	pip install -v .

clean:
	rm -rf dist/ wheel/ build/ *.whl wheelhouse/

cache-clean:
	rm -rf .py-build-cmake_cache/

get-dakota-src:
	rm -rf dakota
	git clone -j4 --branch v6.20.0 --depth 1 https://github.com/snl-dakota/dakota.git
	cd dakota && \
		git submodule update --init packages/external && \
		git submodule update --init packages/pecos && \
		git submodule update --init packages/surfpack && \
		git apply ../dakota-src.patch
