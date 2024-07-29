all:


wheel: cache-clean clean
	CIBW_BUILD=cp311*x86_64 cibuildwheel --platform linux

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
		git apply ../src_patches/dakota-src.patch && \
		git apply --whitespace=nowarn ../src_patches/numpy_pyarray.patch && \
	    find . \( -name \*.cpp -o -name \*.hpp -o -name \*.c -o -name \*.h \) -exec \
			sed -i -f ../src_patches/replace_old_macros_numpy.sed {} +
