all:


wheel:
	pip wheel -v .

install:
	pip install -v .

clean:
	rm -rf dist/ wheel/ build/

cache-clean:
	rm -rf .py-build-cmake_cache/
