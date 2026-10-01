import json
import os
import pathlib as pl
import sys

import pytest

import dakota.environment as dakenv

script_dir = pl.Path(__file__).parent

_WIN32_LP64_BINARY_ARCHIVE = pytest.mark.skipif(
    sys.platform == "win32",
    reason="dakota.rst is a binary Boost archive generated on Linux; its "
    "header records sizeof(long)==8 (LP64) and Boost refuses to load it "
    "where sizeof(long)==4 (LLP64 Windows) — 'incompatible native format - "
    "size of long'. Dakota's binary restart format is not cross-platform; "
    "see SPEC-Windows B26lp",
)


def evaluator(inputs):
    raise Exception("We are supposed to restart from old file")


@_WIN32_LP64_BINARY_ARCHIVE
@pytest.mark.parametrize("input_format", ["classic", "json"])
def test_simple_restart(tmp_path, input_format):
    print("Starting dakota")

    os.chdir(tmp_path)

    if input_format == "json":
        dakota_conf_path = script_dir / "simple.json"
        dakota_conf = json.loads(dakota_conf_path.read_text())
        dakota_conf["environment"]["read_restart"] = {
            "filename": str(script_dir / "dakota.rst")
        }
        study = dakenv.study(
            callbacks={"evaluator": evaluator},
            input_json=dakota_conf,
        )
    else:
        dakota_conf_path = script_dir / "simple.in"
        dakota_conf = dakota_conf_path.read_text()
        study = dakenv.study(
            callbacks={"evaluator": evaluator},
            input_string=dakota_conf,
            read_restart=str(script_dir / "dakota.rst"),
        )

    study.execute()


if __name__ == "__main__":
    test_simple_restart()
