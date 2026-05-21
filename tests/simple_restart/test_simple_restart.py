import json
import os
import pathlib as pl

import pytest

import dakota.environment as dakenv

script_dir = pl.Path(__file__).parent


def evaluator(inputs):
    raise Exception("We are supposed to restart from old file")


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
