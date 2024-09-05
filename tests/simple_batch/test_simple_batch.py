import os
import pathlib as pl

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


def test_simple_batch(tmp_path):
    print("Starting dakota")

    os.chdir(tmp_path)
    dakota_conf_path = script_dir / "simple_batch.in"
    dakota_conf = dakota_conf_path.read_text()
    study = dakenv.study(
        callbacks={"evaluator": batch_evaluator},
        input_string=dakota_conf,
    )

    study.execute()


if __name__ == "__main__":
    test_simple_batch()
