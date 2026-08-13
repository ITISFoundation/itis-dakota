import math
import os

import dakota.environment as dakenv
import pytest

# Regression test for a Dakota EGO bug (introduced in the upstream commit that
# deprecated serial_ego() in favor of batch_synchronous_ego()) where merit
# function (augmented Lagrangian) updates driven by surrogate ("liar") data,
# plus a missing convergence gate, corrupted the final best-point selection
# for constrained problems with a mix of design and (fixed) state variables.
#
# Problem: G3(n=2) with X0 fixed at sqrt(0.5) as a state variable and X1 as
# the sole design variable, subject to X0^2 + X1^2 = 1. The true optimum is
# X1 = sqrt(0.5) (matching X0), since maximizing X0*X1 under that equality
# constraint requires X0 == X1. A regressed EGO returns a value far from this
# optimum (with a correspondingly large constraint violation); a correctly
# converging EGO run lands close to X1 = sqrt(0.5) with a small constraint
# violation.

X0_FIXED = math.sqrt(0.5)


def evaluator(inputs):
    params = inputs["cv"]
    x0, x1 = params
    n = 2
    f = -(x0 * x1) * (math.sqrt(n) ** n)
    g = x0 * x0 + x1 * x1 - 1.0
    return {"fns": [f, g]}


def ego_g3_state_input(seed):
    return f"""
environment
    tabular_data
        tabular_data_file
            'dakota_tabular.dat'
    top_method_pointer = 'EGO'

    method
        id_method = 'EGO'
        efficient_global
            seed = {seed}
            model_pointer = "TRUE_MODEL"

    model
        id_model = 'TRUE_MODEL'
        single
            interface_pointer = 'INTERFACE'
            variables_pointer = 'VARIABLES'
            responses_pointer = 'RESPONSES'

    variables
        id_variables = 'VARIABLES'
        continuous_design = 1
            descriptors       'X1'
            initial_point     0.0
            lower_bounds      0.0
            upper_bounds      1.0
        continuous_state = 1
            descriptors       'X0'
            initial_state     {X0_FIXED!r}
            lower_bounds      0.0
            upper_bounds      1.0

    interface
        id_interface = 'INTERFACE'
        python
            analysis_drivers
                'evaluator'

    responses
        id_responses = 'RESPONSES'
        objective_functions = 1
        nonlinear_equality_constraints = 1
        no_gradients
        no_hessians
"""


@pytest.mark.parametrize("seed", [123456, 111111, 222222, 333333])
def test_ego_state_variable(tmp_path, seed):
    os.chdir(tmp_path)

    study = dakenv.study(
        callbacks={"evaluator": evaluator},
        input_string=ego_g3_state_input(seed),
    )
    study.execute()

    best_x1 = dakenv.get_variable_values(study)[0]

    assert best_x1 == pytest.approx(X0_FIXED, abs=0.05 * X0_FIXED)


if __name__ == "__main__":
    import pathlib as pl

    test_ego_state_variable(pl.Path("."), 123456)
