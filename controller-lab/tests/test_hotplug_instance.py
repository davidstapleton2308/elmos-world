"""Regression guard: emulation must bind to a stable SDL instance, not a list index."""
import ast
import inspect

from elmos_controller_lab import lab


def test_emulation_pins_physical_instance_across_hotplug():
    tree = ast.parse(inspect.getsource(lab.command_emulate))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)]
    assert any(node.func.attr == "read_instance" and len(node.args) == 1
               and isinstance(node.args[0], ast.Name)
               and node.args[0].id == "physical_instance" for node in calls)
    assert not any(node.func.attr == "read" and isinstance(node.func.value, ast.Name)
                   and node.func.value.id == "source" for node in calls)


def test_matrix_also_reads_pinned_instance():
    tree = ast.parse(inspect.getsource(lab.command_matrix))
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr == "read_instance" for node in ast.walk(tree))
