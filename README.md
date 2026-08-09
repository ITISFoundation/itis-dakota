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

Dakota's native JSON input format
----------------------------------

Since Dakota 6.24, studies can be configured directly from JSON instead of
Dakota's legacy keyword input file. Dakota's own Pydantic v2 models for that
JSON format (`dakota/python/dakota/spec`, source of truth for `dakota.json`
and the C++ JSON parser) are shipped as `dakota.spec`, giving IDE
autocomplete/inline docs and real validation without a round-trip to the
online docs:

```python
from dakota.spec import DakotaStudy
import dakota.environment as dakenv

study = DakotaStudy(
    method=[...],
    variables=[...],
    responses=[...],
)
dakenv.study(callback, study.model_dump(mode="json", exclude_none=True))
```

`dakota.spec` is pure Python (no compiled dependency) and is copied
verbatim from the vendored Dakota source on each build, so it stays in
sync with whatever Dakota version this wheel bundles automatically.

Copyright (c) 2023-2026 IT'IS Foundation, Zurich, Switzerland
