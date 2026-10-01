#!/usr/bin/env bash
# Run inside MSYS2 (ucrt64) on Windows from the repo root, after pacman
# boost+gcc are installed (the wheels-windows CI job does this explicitly;
# cibuildwheel before-all cannot, as it gets no repo-root cwd on windows).
#
# Why this exists: Boost.Regex went header-only in Boost 1.92 — upstream's
# CMake superproject builds it as `add_library(boost_regex INTERFACE)` (see
# boostorg/regex@boost-1.92.0/CMakeLists.txt) and MSYS2 accordingly installs
# no libboost_regex at all. Dakota's Boost discovery is module mode
# (Boost_NO_BOOST_CMAKE=ON, because pacman's BoostConfig targets MSVC-style
# library names) and module-mode FindBoost insists on a REAL library file per
# component, so find_package(Boost COMPONENTS ... regex ...) hard-fails
# "missing: regex" even though every symbol Dakota's boost::regex uses is
# header-inlined.
#
# Fix with the smallest possible blast radius: compile the only compiled
# sources Boost.Regex 1.92 still ships (the C POSIX-API shims) into the
# pacman-named static archive and drop it where FindBoost looks. Which
# matches how the other components already resolve (Boost_USE_STATIC_LIBS
# is forced ON for WIN32 by Dakota, MSYS2 layout=tagged => *_-mt.a names).
# The archive's contents are never actually referenced by Dakota (it uses
# the C++ API only, header-inlined); it just has to exist and link cleanly.
set -euo pipefail

BOOST_TAG=boost-1.92.0            # must match pacman's mingw-w64-ucrt-x86_64-boost
PREFIX=/ucrt64
OUT="$PREFIX/lib/libboost_regex-mt.a"

if [[ -f "$OUT" ]]; then
  echo "build_boost_regex: $OUT already present, nothing to do"
  exit 0
fi

# Guard against silent version drift if pacman's boost moves past the tag.
installed=$(sed -n 's/.*#define BOOST_LIB_VERSION "\([^"]*\)".*/\1/p' "$PREFIX/include/boost/version.hpp")
if [[ "$installed" != "1_92" ]]; then
  echo "build_boost_regex: pacman boost is $installed, script pins $BOOST_TAG;" >&2
  echo "build_boost_regex: bump BOOST_TAG (and re-check that regex is still" >&2
  echo "build_boost_regex: shim-only sources) in scripts/build_boost_regex.sh" >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

curl -fsSL "https://codeload.github.com/boostorg/regex/tar.gz/refs/tags/$BOOST_TAG" \
  | tar xz -C "$work"
src="$work/regex-$BOOST_TAG"

# -I the module's own headers first so the shims see their matching-version
# public headers; the rest of boost (config, assert, ...) comes from the
# pacman-installed tree, which the ucrt64 g++ searches by default.
"$PREFIX/bin/g++" -c -O2 -DNDEBUG -DBOOST_REGEX_NO_LIB=1 \
  -I "$src/include" \
  -o "$work/posix_api.o"        "$src/src/posix_api.cpp"
"$PREFIX/bin/g++" -c -O2 -DNDEBUG -DBOOST_REGEX_NO_LIB=1 \
  -I "$src/include" \
  -o "$work/wide_posix_api.o"   "$src/src/wide_posix_api.cpp"

"$PREFIX/bin/ar" rcs "$work/libboost_regex-mt.a" "$work"/*.o
"$PREFIX/bin/ranlib" "$work/libboost_regex-mt.a"
install -Dm644 "$work/libboost_regex-mt.a" "$OUT"
echo "build_boost_regex: installed $OUT ($(stat -c%s "$OUT") bytes)"
