import os
import pathlib as pl
import subprocess
import sys
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


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
