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

Copyright (c) 2023-2024 IT'IS Foundation, Zurich, Switzerland
