"""Regression: a failed neutral report must not skip virtual slot destruction."""
import ast
import inspect

from elmos_controller_lab import lab


def test_emulate_cleanup_attempts_destroy_after_neutral_failure():
    tree = ast.parse(inspect.getsource(lab.command_emulate))
    cleanup = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Call)
        and isinstance(node.iter.func, ast.Name)
        and node.iter.func.id == "reversed"
        and len(node.iter.args) == 1
        and isinstance(node.iter.args[0], ast.Name)
        and node.iter.args[0].id == "created_slots"
    )
    # Separate top-level try statements ensure a neutral-send exception
    # cannot bypass the subsequent destroy attempt.
    tries = [node for node in cleanup.body if isinstance(node, ast.Try)]
    assert len(tries) >= 2
    destroy_calls = [
        node for node in ast.walk(tries[1])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "request"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "destroy"
    ]
    assert destroy_calls
