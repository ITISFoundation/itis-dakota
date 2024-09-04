import os
import pathlib as pl

import dakota.environment as dakenv

script_dir = pl.Path(__file__).parent


def evaluator(inputs):
    # Get the continuous variables out of the input provided by dakota
    params = inputs["cv"]
    print(f"Evaluating {params}")

    # Put the objective in the dakota 'fns' field of the output
    outputs = {"fns": params, "failure": 1}

    #return Exception()
    return outputs


def test_simple(tmp_path):
    os.chdir(tmp_path)

    print("Starting dakota")

    dakota_conf_path = script_dir / "simple.in"
    dakota_conf = dakota_conf_path.read_text()
    study = dakenv.study(
        callbacks={"evaluator": evaluator},
        input_string=dakota_conf,
    )

    study.execute()


if __name__ == "__main__":
    test_simple()
