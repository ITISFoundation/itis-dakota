Dakota wheel built by the IT'IS Foundation
==========================================

[![build-wheel](https://github.com/ITISFoundation/itis-dakota/actions/workflows/build-wheels.yml/badge.svg)](https://github.com/ITISFoundation/itis-dakota/actions/workflows/build-wheels.yml)

This repository contains the code to build a Python wheel
to load the [Dakota](https://github.com/snl-dakota/dakota) 
python module.


Installing the wheel
----------------------

```
pip install itis-dakota
```

Requirements
------------

At the moment the wheel can be installed on **Linux** ([manylinux_2_28](https://github.com/pypa/manylinux) compatible distributions) only.

Support for other operating systems will be added in the future.

Using the wheel
------------------

After installation, the module can be imported:
```
import dakota
import dakota.environment as dakenv
```

And example on how to use the environment module can be found here:
https://github.com/snl-dakota/dakota/blob/devel/src/unit/test_dakota_python_env.py

Building the wheel
------------------

```
make wheel
```

Typing / stubs
--------------

`dakota.environment` is a compiled pybind11 extension, so its type stubs
(`stubs/dakota/environment/{__init__.pyi,environment.pyi}`) are generated,
not hand-written. After bumping the Dakota version or touching
`dakota/src/dakota_python.cpp` via a patch, rebuild the wheel and
regenerate the stubs, then commit the result:

```
make wheel
make stubs
```

CI flags (via a warn-only annotation, does not fail the build) if the
committed stubs no longer match the compiled module.

Copyright (c) 2023-2026 IT'IS Foundation, Zurich, Switzerland
