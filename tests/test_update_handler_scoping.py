"""Regression test: avoid shadowing the game process guard in update handlers."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / 'app' / 'server.py'


class UpdateHandlerScopeTests(unittest.TestCase):
    def test_game_guard_is_not_shadowed_inside_post_handler(self):
        tree = ast.parse(SERVER.read_text(encoding='utf-8'), filename=str(SERVER))
        module_imported = any(
            isinstance(node, ast.ImportFrom)
            and node.module == 'backend'
            and any(alias.name == 'active_game_process' for alias in node.names)
            for node in tree.body
        )
        self.assertTrue(module_imported, 'Expected module-level active_game_process import')

        handlers = [
            fn for cls in tree.body if isinstance(cls, ast.ClassDef)
            for fn in cls.body if isinstance(fn, ast.FunctionDef) and fn.name == 'do_POST'
        ]
        self.assertEqual(len(handlers), 1)
        method = handlers[0]
        for node in ast.walk(method):
            if isinstance(node, ast.ImportFrom):
                names = [alias.asname or alias.name for alias in node.names]
                self.assertNotIn(
                    'active_game_process', names,
                    'An import inside do_POST shadows active_game_process throughout '
                    'the function and crashes the in-app updater.'
                )
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                self.assertNotEqual(node.id, 'active_game_process')


if __name__ == '__main__':
    unittest.main()
