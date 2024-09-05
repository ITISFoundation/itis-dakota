import os
import pathlib as pl

import dakota.environment as dakenv

script_dir = pl.Path(__file__).parent


def evaluator(inputs):
    raise Exception("We are supposed to restart from old file")


def test_simple_restart(tmp_path):
    print("Starting dakota")

    os.chdir(tmp_path)

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
