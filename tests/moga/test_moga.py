import json
import os
import pathlib as pl
import subprocess
import sys

import pytest

import dakota.environment as dakenv

script_dir = pl.Path(__file__).parent


def evaluate(x, y, z):
    # Objective 1: Minimize the sum of squares
    obj1 = x**2 + y**2 + z**2

    # Objective 2: Maximize the product
    obj2 = -(x * y * z)  # Negated because we conventionally minimize

    return obj1, obj2


def evaluator(inputs):
    # Get the continuous variables out of the input provided by dakota
    params = inputs["cv"]
    # print(f"Evaluating {params}")

    # Put the objective in the dakota 'fns' field of the output
    outputs = {"fns": evaluate(*params)}
    return outputs


@pytest.mark.parametrize("input_format", ["classic", "json"])
def test_moga(tmp_path, input_format):
    """Test MOGA - runs in subprocess due to Dakota global state limitation."""
    result = subprocess.run(
        [sys.executable, __file__, input_format, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        result.returncode == 0
    ), f"MOGA test ({input_format}) failed:\n{result.stderr}"


def _run_moga(input_format, tmp_path):
    os.chdir(tmp_path)

    if input_format == "json":
        dakota_conf_path = script_dir / "moga.json"
        dakota_conf = json.loads(dakota_conf_path.read_text())
        study = dakenv.study(
            callbacks={"evaluator": evaluator},
            input_json=dakota_conf,
        )
    else:
        dakota_conf_path = script_dir / "moga.in"
        dakota_conf = dakota_conf_path.read_text()
        study = dakenv.study(
            callbacks={"evaluator": evaluator},
            input_string=dakota_conf,
        )

    study.execute()


if __name__ == "__main__":
    input_format = sys.argv[1] if len(sys.argv) > 1 else "classic"
    tmp_path = pl.Path(sys.argv[2]) if len(sys.argv) > 2 else pl.Path("/tmp")
    _run_moga(input_format, tmp_path)
