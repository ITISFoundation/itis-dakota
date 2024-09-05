import os
import pathlib as pl

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
    #print(f"Evaluating {params}")

    # Put the objective in the dakota 'fns' field of the output
    outputs = {"fns": evaluate(*params)}
    return outputs


def test_moga(tmp_path):
    print("Starting dakota")

    os.chdir(tmp_path)
    dakota_conf_path = script_dir / "moga.in"
    dakota_conf = dakota_conf_path.read_text()
    study = dakenv.study(
        callbacks={"evaluator": evaluator},
        input_string=dakota_conf,
    )

    study.execute()


if __name__ == "__main__":
    test_moga()
