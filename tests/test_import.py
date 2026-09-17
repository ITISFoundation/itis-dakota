def test_import_dakota():
    import dakota

def test_import_env():
    import dakota.environment as dakenv

def test_spec_ships_py_typed():
    # dakota/ is a namespace package, so dakota/environment's py.typed does
    # not cover dakota.spec (PEP 561): it needs its own marker or type
    # checkers ignore its inline annotations.
    from pathlib import Path

    import dakota.spec

    assert (Path(dakota.spec.__file__).parent / "py.typed").is_file()

def test_import_spec():
    from dakota.spec.study import DakotaStudy

    # Note: dakota.spec validates presence-flag fields (e.g. sample_type.lhs)
    # as the literal `True`, unlike the looser `{}` the C++ JSON parser
    # accepts for `input_json=...` (see tests/simple/simple.json).
    study = DakotaStudy.model_validate(
        {
            "method": [{"sampling": {"sample_type": {"lhs": True}, "samples": 10}}],
            "variables": [
                {
                    "continuous_design": {
                        "count": 2,
                        "descriptors": ["PARAM1", "PARAM2"],
                        "lower_bounds": [0.0, 0.0],
                        "upper_bounds": [1.0, 2.0],
                    }
                }
            ],
            "responses": [
                {
                    "descriptors": ["OBJ1"],
                    "response_type": {"objective_functions": {"count": 1}},
                    "gradient_type": {"no_gradients": True},
                    "hessian_type": {"no_hessians": True},
                }
            ],
        }
    )
    assert study.model_dump(exclude_none=True)["variables"][0]["continuous_design"]["count"] == 2
