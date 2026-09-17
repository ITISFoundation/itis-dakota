#!/usr/bin/env python3
"""Normalize a pybind11-stubgen-generated dakota.environment stub in place.

Shared by scripts/generate_stubs.sh and the CI stub-drift check in
.github/workflows/buildwheels.yml so both apply identical fixups.
"""
import re
import sys

# pybind11-stubgen can't see through the py::object/py::dict C++ params to
# the actual callable contract (traced via Pybind11Interface::derived_map_ac:
# a per-evaluation callback is invoked as callback(kwargs) -> dict; a batch
# callback (interface.concurrency.batch) is invoked as
# callback(list[kwargs]) -> Iterable[dict]; `callbacks` is dict[str, <either
# callback shape>] keyed by analysis-driver id).
CALLBACK_ALIASES = (
    "DakotaEvaluatorCallback = typing.Callable[[dict[str, typing.Any]], dict[str, typing.Any]]\n"
    '"""Per-evaluation analysis-driver callback: receives a params dict (variable\n'
    "values/labels/ASV, either as numpy arrays or lists depending on the\n"
    '`numpy` interface option) and must return a response dict."""\n'
    "DakotaBatchCallback = typing.Callable[[list[dict[str, typing.Any]]], typing.Iterable[dict[str, typing.Any]]]\n"
    '"""Batch analysis-driver callback (used with `interface.concurrency.batch`):\n'
    "receives a list of per-evaluation params dicts and must return/yield one\n"
    'response dict per input, in the same order."""\n'
    "DakotaCallback = typing.Union[DakotaEvaluatorCallback, DakotaBatchCallback]\n"
    '"""Either callback shape accepted by `study(callback=...)` / `callbacks={...}`."""\n'
)


def normalize(text: str) -> str:
    # pybind11-stubgen can't resolve the nlohmann::json/pybind11_json binding
    # to a real Python type and emits a bare, unimported `json` annotation on
    # the study(..., input_json) overloads. Normalize it to typing.Any
    # (accurate: any JSON-serializable Python value) so the stub is valid.
    text = text.replace(": json)", ": typing.Any)")

    # Insert the callback aliases right after the module's __all__ line.
    marker = "__all__: list[str] = "
    idx = text.index(marker)
    line_end = text.index("\n", idx) + 1
    text = text[:line_end] + CALLBACK_ALIASES + text[line_end:]

    # Replace the untyped `callback: typing.Any` / bare `callbacks: dict`
    # with the proper Callable alias instead of leaving them as Any / an
    # unparameterized dict.
    text = text.replace("callback: typing.Any", "callback: DakotaCallback")
    text = re.sub(r"callbacks: dict(?!\[)", "callbacks: dict[str, DakotaCallback]", text)

    # pybind11-stubgen emits `numpy.ndarray[numpy.float64]`, but
    # numpy.ndarray's single type-parameter is the shape, not the dtype (a
    # type checker reports this as invalid). Use the correctly-parameterized
    # numpy.typing.NDArray.
    text = text.replace("import numpy\n", "import numpy\nimport numpy.typing\n", 1)
    text = text.replace(
        "numpy.ndarray[numpy.float64]", "numpy.typing.NDArray[numpy.float64]"
    )

    return text


def main() -> None:
    path = sys.argv[1]
    with open(path) as f:
        text = f.read()
    with open(path, "w") as f:
        f.write(normalize(text))


if __name__ == "__main__":
    main()
