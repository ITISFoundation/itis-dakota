import json
import os
import pathlib as pl

import pytest

import dakota.environment as dakenv

script_dir = pl.Path(__file__).parent


def evaluator(inputs):
    # Get the continuous variables out of the input provided by dakota
    params = inputs["cv"]
    print(f"Evaluating {params}")

    # Put the objective in the dakota 'fns' field of the output
    outputs = {"fns": params}
    return outputs


def batch_evaluator(batch_input):
    return map(evaluator, batch_input)


@pytest.mark.parametrize("input_format", ["classic", "json"])
def test_simple_batch(tmp_path, input_format):
    print("Starting dakota")

    os.chdir(tmp_path)

    if input_format == "json":
        dakota_conf_path = script_dir / "simple_batch.json"
        dakota_conf = json.loads(dakota_conf_path.read_text())
        study = dakenv.study(
            callbacks={"evaluator": batch_evaluator},
            input_json=dakota_conf,
        )
    else:
        dakota_conf_path = script_dir / "simple_batch.in"
        dakota_conf = dakota_conf_path.read_text()
        study = dakenv.study(
            callbacks={"evaluator": batch_evaluator},
            input_string=dakota_conf,
        )

    study.execute()


if __name__ == "__main__":
    test_simple_batch()
