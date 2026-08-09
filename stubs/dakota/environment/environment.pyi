from __future__ import annotations
import numpy
import typing
__all__: list[str] = ['CommandLine', 'Response', 'Variables', 'build_info', 'get_response_fn_val', 'get_variable_values', 'get_variable_values_np', 'print_version', 'revision', 'study', 'version']
class CommandLine:
    def __init__(self, arg0: str) -> None:
        ...
    def execute(self) -> None:
        ...
class Response:
    def __init__(self) -> None:
        ...
    def function_value(self, i: int) -> float:
        """
        Return function value by index
        """
class Variables:
    def __init__(self) -> None:
        ...
    def num_active_cv(self) -> int:
        """
        Return number of active continuous vars
        """
class study:
    @typing.overload
    def __init__(self, callback: typing.Any, input_string: str, read_restart: str = '') -> None:
        ...
    @typing.overload
    def __init__(self, callbacks: dict, input_string: str, read_restart: str = '') -> None:
        ...
    @typing.overload
    def __init__(self, callback: typing.Any, input_json: typing.Any) -> None:
        ...
    @typing.overload
    def __init__(self, callbacks: dict, input_json: typing.Any) -> None:
        ...
    def execute(self) -> None:
        ...
    def response_results(self) -> Response:
        ...
    def variables_results(self) -> Variables:
        ...
def build_info(query: str = 'CXX') -> list[str]:
    """
    Return build information related to `query' as a string
    """
def get_response_fn_val(arg0: study) -> float:
    """
    Get final Response function value
    """
def get_variable_values(arg0: study) -> list[float]:
    """
    Get active continuous Variable values
    """
def get_variable_values_np(arg0: study) -> numpy.ndarray[numpy.float64]:
    """
    Get active continuous Variable values
    """
def print_version(query: str = '') -> None:
    """
    Print Dakota version to console
    """
def revision() -> str:
    """
    Return Dakota repository revision number as string
    """
def version() -> str:
    """
    Return Dakota version as string
    """
