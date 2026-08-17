import os
import subprocess

import pytest

# Regression test for a Dakota crash (SIGSEGV / Windows 0xC0000005) that occurs
# when the "dakota" Gaussian process backend is combined with results_output.
#
# GaussProcApproximation::optimize_theta_global() fits the GP hyperparameters
# with a nested NCSUOptimizer built via the "user functions" (callback)
# constructor, which deliberately leaves iteratedModel null. When the results
# database is active, that optimizer's post_run() reaches
# Minimizer::archive_best_results(), which dereferenced original_model()
# (i.e. iteratedModel) unconditionally.
#
# Only `gaussian_process dakota` triggers it; `surfpack` uses its own optimizer.

DAKOTA_INPUT = """
environment,
  tabular_data
    tabular_data_file = "iterations_result.dat"
    results_output

method,
    efficient_global
        gaussian_process dakota
        seed = 123456
        max_iterations = 3

variables,
    continuous_design = 2
    initial_point    0.35  0.35
    upper_bounds     1.5   1.5
    lower_bounds     0.35  0.35
    descriptors      "X0"  "X1"

interface,
    analysis_driver = "rosenbrock_driver.py"
        fork
        file_tag
        parameters_file = "params.in"
        results_file = "results.out"
    failure_capture = abort

responses,
    objective_functions = 1
    no_gradients
    no_hessians
"""

DRIVER = """#!/usr/bin/env python3
import sys

params_file, results_file = sys.argv[1], sys.argv[2]

vals = {}
with open(params_file) as fh:
    for line in fh:
        parts = line.split()
        if len(parts) == 2:
            vals[parts[1]] = parts[0]

x = [float(vals[k]) for k in sorted(k for k in vals if k.startswith("X"))]
f = sum(100.0 * (x[i + 1] - x[i] ** 2) ** 2 + (x[i] - 1.0) ** 2 for i in range(len(x) - 1))

with open(results_file, "w") as fh:
    fh.write(f"{f:.16e} f\\n")
"""


def test_ego_dakota_gp_results_output(tmp_path):
    os.chdir(tmp_path)

    driver = tmp_path / "rosenbrock_driver.py"
    driver.write_text(DRIVER)
    driver.chmod(0o755)

    input_file = tmp_path / "ego_dakota_gp.in"
    input_file.write_text(DAKOTA_INPUT)

    result = subprocess.run(
        ["dakota", "-i", input_file.name],
        capture_output=True,
        text=True,
        timeout=600,
    )

    assert result.returncode == 0, (
        f"dakota exited with {result.returncode}\n{result.stdout[-2000:]}"
    )
    assert (tmp_path / "dakota_results.txt").exists()
