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
    "see SPEC-Windows B26lp. Coverage note (V15nb/B32): what this skip "
    "removes is loading a FOREIGN archive — irreducibly impossible on "
    "win32; same-platform restart coverage lives in "
    "test_simple_restart_same_platform_roundtrip below, which runs here",
)


def evaluator(inputs):
    raise Exception("We are supposed to restart from old file")


def ok_evaluator(inputs):
    return {"fns": inputs["cv"], "failure": 1}


def test_simple_restart_same_platform_roundtrip(tmp_path):
    """Generate the restart archive on THIS platform (portable callback
    interface), then restart from it: the phase-2 evaluator raises, so a
    green run is proof dakota short-circuited evaluation from the archive.
    This is what win32's restart coverage looks like now that the LP64-
    gated test above can only ever exercise cross-OS archive loading
    elsewhere (V15nb/B32)."""
    os.chdir(tmp_path)
    archive = tmp_path / "dakota_roundtrip.rst"

    # Phase 1: plain run, writing the restart archive.
    conf = (script_dir / "simple.in").read_text()
    conf = conf.replace(
        "'dakota_tabular.dat'",
        "'dakota_tabular.dat'\n    write_restart 'dakota_roundtrip.rst'",
        1,
    )
    study = dakenv.study(
        callbacks={"evaluator": ok_evaluator},
        input_string=conf,
    )
    study.execute()
    assert archive.exists(), "write_restart produced no archive"

    # Phase 2: restart with the raising evaluator.
    conf2 = (script_dir / "simple.in").read_text()
    conf2 = conf2.replace(
        "'dakota_tabular.dat'",
        "'dakota_tabular.dat'\n    read_restart 'dakota_roundtrip.rst'",
        1,
    )
    study2 = dakenv.study(
        callbacks={"evaluator": evaluator},
        input_string=conf2,
    )
    study2.execute()


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
