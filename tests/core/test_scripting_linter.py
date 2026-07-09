from __future__ import annotations

from nyxor.core.scripting import lint_source


def test_function_body_sees_names_imported_before_it() -> None:
    # Regression: a function calling a library function via its import alias
    # used to be flagged as referencing an undefined variable, even though
    # it runs fine (NyxFunction.home_env gives it real access to the
    # enclosing scope at call time).
    issues = lint_source(
        """
import "lib/findings.nyx" as findings

func print_summary(results, target):
    set total = findings.total_findings(results)
    print total
end
"""
    )
    assert issues == []


def test_function_body_sees_module_level_variables_set_before_it() -> None:
    issues = lint_source(
        """
set threshold = 5

func over_threshold(n):
    return n > threshold
end
"""
    )
    assert issues == []


def test_function_body_still_flags_a_genuinely_undefined_variable() -> None:
    issues = lint_source(
        """
func broken():
    print totally_undefined_thing
end
"""
    )
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "totally_undefined_thing" in issues[0].message


def test_function_body_does_not_see_names_defined_after_it() -> None:
    # Still order-sensitive, like every other `set` in the linter — a
    # function can forward-reference other *functions* (see
    # _collect_function_names) but not plain variables.
    issues = lint_source(
        """
func uses_later():
    print later_var
end
set later_var = 1
"""
    )
    assert len(issues) == 1
    assert "later_var" in issues[0].message


def test_function_parameters_still_shadow_and_are_visible() -> None:
    issues = lint_source(
        """
func square(x):
    return x * x
end
"""
    )
    assert issues == []
