import os
import pathlib as pl
import subprocess
import tempfile


def test_dakota_executable_exists():
    """Test that the dakota executable is available in the PATH."""
    result = subprocess.run(["dakota", "--version"], capture_output=True, text=True)
    # Dakota --version returns non-zero exit code but prints version info
    assert "Dakota version" in result.stdout or "Dakota version" in result.stderr


def test_dakota_executable_help():
    """Test that dakota executable can display help."""
    result = subprocess.run(["dakota", "--help"], capture_output=True, text=True)
    # Help should mention usage or options
    output = result.stdout + result.stderr
    assert "usage" in output.lower() or "dakota" in output.lower()


def test_dakota_executable_run_simple():
    """Test that dakota executable can run a simple input file."""
    # Create a simple dakota input file with system interface
    dakota_input = """
environment
    tabular_data
        tabular_data_file 'dakota_tabular.dat'

method
    sampling
        sample_type lhs
        samples 5
        seed 12345

variables
    uniform_uncertain = 2
        lower_bounds    0.0  0.0
        upper_bounds    1.0  1.0
        descriptors    'x1' 'x2'

interface
    analysis_drivers = 'echo'
    fork

responses
    response_functions = 1
    no_gradients
    no_hessians
"""

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pl.Path(tmp_dir)
        input_file = tmp_path / "dakota_test.in"
        input_file.write_text(dakota_input)

        # Run dakota with the input file
        result = subprocess.run(
            ["dakota", "-i", str(input_file), "-o", str(tmp_path / "dakota.out")],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Check that dakota ran (exit code 0 or that it produced output)
        assert (
            result.returncode == 0 or (tmp_path / "dakota.out").exists()
        ), f"Dakota failed with: {result.stderr}"

        # Check that tabular data was created
        assert (
            tmp_path / "dakota_tabular.dat"
        ).exists(), "Dakota did not create tabular output file"


def test_dakota_executable_check_syntax():
    """Test that dakota executable can check input file syntax."""
    dakota_input = """
environment
    tabular_data
        tabular_data_file 'test.dat'

method
    sampling
        samples 5

variables
    uniform_uncertain = 1
        lower_bounds 0.0
        upper_bounds 1.0

interface
    analysis_drivers = 'echo'
    fork

responses
    response_functions = 1
    no_gradients
    no_hessians
"""

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pl.Path(tmp_dir)
        input_file = tmp_path / "syntax_test.in"
        input_file.write_text(dakota_input)

        # Run dakota with -check flag to validate syntax
        result = subprocess.run(
            ["dakota", "-check", "-i", str(input_file)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Check flag should succeed for valid input
        output = result.stdout + result.stderr
        assert (
            result.returncode == 0 or "parsed" in output.lower()
        ), f"Dakota syntax check failed: {result.stderr}"


def test_dakota_executable_moga():
    """Test that dakota executable can run multi-objective genetic algorithm."""
    # Use a simpler approach with echo to avoid script complexity
    dakota_input = """
environment
    tabular_data
        tabular_data_file 'dakota_moga.dat'

method
    moga
        seed 12345
        max_function_evaluations 30
        population_size 10

variables
    continuous_design = 2
        lower_bounds   -2.0  -2.0
        upper_bounds    2.0   2.0
        descriptors    'x1'  'x2'

interface
    analysis_drivers = 'rosenbrock'
    fork
    parameters_file = 'params.in'
    results_file = 'results.out'
    file_tag
    file_save

responses
    objective_functions = 2
    no_gradients
    no_hessians
"""

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pl.Path(tmp_dir)
        input_file = tmp_path / "moga_test.in"
        input_file.write_text(dakota_input)

        # Create a simple Python script for rosenbrock evaluation
        rosenbrock_script = tmp_path / "rosenbrock"
        rosenbrock_script.write_text(
            """#!/usr/bin/env python3
import sys
import os

# Read params.in file
params_file = sys.argv[1] if len(sys.argv) > 1 else 'params.in'
results_file = sys.argv[2] if len(sys.argv) > 2 else 'results.out'

with open(params_file, 'r') as f:
    lines = f.readlines()
    # Skip first line (num variables), read x1 and x2
    x1 = float(lines[1].split()[0])
    x2 = float(lines[2].split()[0])

# Calculate objectives
# f1 = Rosenbrock: (x1-1)^2 + 100*(x2-x1^2)^2
# f2 = sum of squares: x1^2 + x2^2
f1 = (x1 - 1)**2 + 100 * (x2 - x1**2)**2
f2 = x1**2 + x2**2

# Write results
with open(results_file, 'w') as f:
    f.write(f"{f1} obj1\\n")
    f.write(f"{f2} obj2\\n")
"""
        )
        rosenbrock_script.chmod(0o755)

        # Run dakota with the MOGA input
        result = subprocess.run(
            ["dakota", "-i", str(input_file), "-o", str(tmp_path / "dakota.out")],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Debug output if failed
        if result.returncode != 0:
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            if (tmp_path / "dakota.out").exists():
                print(f"Dakota output: {(tmp_path / 'dakota.out').read_text()}")

        # Check that dakota ran successfully
        assert (
            result.returncode == 0
        ), f"Dakota MOGA failed with return code {result.returncode}: {result.stderr}"

        # Check that tabular data was created and has content
        tabular_file = tmp_path / "dakota_moga.dat"
        assert tabular_file.exists(), "Dakota did not create MOGA tabular output"

        # Verify some evaluations were performed
        content = tabular_file.read_text()
        # Count non-comment, non-empty lines
        data_lines = [
            line
            for line in content.split("\n")
            if line.strip() and not line.strip().startswith("%")
        ]

        # Should have header + data rows
        assert (
            len(data_lines) > 2
        ), f"Not enough MOGA evaluations performed. Found {len(data_lines)} lines in tabular file"


def test_dakota_executable_restart():
    """Test that dakota executable can restart from a restart file."""
    # First run - create restart file
    dakota_input_first = """
environment
    tabular_data
        tabular_data_file 'dakota_first.dat'
    write_restart 'dakota.rst'

method
    sampling
        sample_type lhs
        samples 5
        seed 12345

variables
    uniform_uncertain = 2
        lower_bounds   0.0  0.0
        upper_bounds   1.0  1.0
        descriptors   'x1' 'x2'

interface
    analysis_drivers = './driver'
    fork

responses
    response_functions = 1
    no_gradients
    no_hessians
"""

    # Second run - restart and add more samples
    dakota_input_restart = """
environment
    tabular_data
        tabular_data_file 'dakota_restart.dat'
    read_restart 'dakota.rst'
    write_restart 'dakota.rst'

method
    sampling
        sample_type lhs
        samples 10
        seed 12345

variables
    uniform_uncertain = 2
        lower_bounds   0.0  0.0
        upper_bounds   1.0  1.0
        descriptors   'x1' 'x2'

interface
    analysis_drivers = './driver'
    fork

responses
    response_functions = 1
    no_gradients
    no_hessians
"""

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pl.Path(tmp_dir)

        # Create a simple driver script that handles Dakota's fork interface
        driver_script = tmp_path / "driver"
        driver_script.write_text(
            """#!/usr/bin/env python3
import sys
import os

# Dakota fork interface passes params_file and results_file as arguments
params_file = sys.argv[1]
results_file = sys.argv[2]

try:
    # Read parameters
    with open(params_file, 'r') as f:
        lines = f.readlines()
        # Line 0: number of variables
        # Line 1+: variable_value variable_name
        x1 = float(lines[1].split()[0])
        x2 = float(lines[2].split()[0])

    # Calculate simple response: sum of inputs
    result = x1 + x2

    # Write results in Dakota format
    with open(results_file, 'w') as f:
        f.write(f"{result} response\\n")
    
    # Exit with success
    sys.exit(0)
    
except Exception as e:
    # Write error to stderr
    print(f"Driver error: {e}", file=sys.stderr)
    print(f"Params file: {params_file}", file=sys.stderr)
    print(f"Results file: {results_file}", file=sys.stderr)
    
    # Still try to create results file to avoid Dakota error
    try:
        with open(results_file, 'w') as f:
            f.write("0.0 response\\n")
    except:
        pass
    
    sys.exit(1)
"""
        )
        driver_script.chmod(0o755)

        # First run - create restart file
        input_file_1 = tmp_path / "dakota_first.in"
        input_file_1.write_text(dakota_input_first)

        result1 = subprocess.run(
            ["dakota", "-i", str(input_file_1)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        if result1.returncode != 0:
            print(f"First run STDOUT: {result1.stdout}")
            print(f"First run STDERR: {result1.stderr}")
            # Check if driver was created and is executable
            print(f"Driver exists: {driver_script.exists()}")
            print(f"Driver executable: {os.access(driver_script, os.X_OK)}")
            # List files in tmp_path
            print(f"Files in {tmp_path}: {list(tmp_path.iterdir())}")

        assert result1.returncode == 0, f"First run failed: {result1.stderr}"
        assert (tmp_path / "dakota.rst").exists(), "Restart file not created"
        assert (
            tmp_path / "dakota_first.dat"
        ).exists(), "First tabular file not created"

        # Second run - restart from file
        input_file_2 = tmp_path / "dakota_restart.in"
        input_file_2.write_text(dakota_input_restart)

        result2 = subprocess.run(
            ["dakota", "-i", str(input_file_2)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        if result2.returncode != 0:
            print(f"Restart run STDOUT: {result2.stdout}")
            print(f"Restart run STDERR: {result2.stderr}")

        assert result2.returncode == 0, f"Restart run failed: {result2.stderr}"
        assert (
            tmp_path / "dakota_restart.dat"
        ).exists(), "Restart tabular file not created"

        # Verify restart had effect (should have evaluations)
        restart_content = (tmp_path / "dakota_restart.dat").read_text()
        restart_lines = [
            l
            for l in restart_content.split("\n")
            if l.strip() and not l.strip().startswith("%")
        ]

        # Should have at least header + some data
        assert (
            len(restart_lines) >= 2
        ), f"Restart run did not produce expected evaluations. Found {len(restart_lines)} lines"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
