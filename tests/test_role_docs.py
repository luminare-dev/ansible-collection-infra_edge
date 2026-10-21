"""Keep the role documentation and defaults equal to meta/argument_specs.yml.

Every role variable is declared once in roles/<role>/meta/argument_specs.yml. These tests fail
when defaults/main.yml and argument_specs.yml disagree, when a variable has no description or no
role prefix, or when a variable table in a README or in docs/configuration.md is out of date
(fix: python3 tests/role_docs.py --write). They need PyYAML (requirements-test.txt).
"""

from __future__ import annotations

import unittest
from pathlib import Path

try:
    import yaml

    import role_docs
except ImportError:  # pragma: no cover - only without the test requirements
    yaml = None
    role_docs = None

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipIf(yaml is None, "PyYAML is not installed (pip install -r requirements-test.txt)")
class ArgumentSpecsTest(unittest.TestCase):
    def test_every_role_has_argument_specs(self):
        roles = [d.name for d in sorted((ROOT / "roles").iterdir()) if (d / "tasks").is_dir()]
        self.assertEqual(roles, role_docs.role_names())

    def test_defaults_match_argument_specs(self):
        for role in role_docs.role_names():
            with self.subTest(role=role):
                options = role_docs.load_options(role)
                defaults_file = ROOT / "roles" / role / "defaults" / "main.yml"
                defaults = yaml.safe_load(defaults_file.read_text(encoding="utf-8"))
                self.assertEqual(sorted(defaults), sorted(options),
                                 "defaults/main.yml and argument_specs.yml list different variables")
                for name, spec in options.items():
                    self.assertTrue(name.startswith(f"{role}_"), f"{name}: variables start with the role name")
                    self.assertIn("default", spec, f"{name}: argument_specs.yml has no default")
                    self.assertEqual(spec["default"], defaults[name], f"{name}: defaults differ")
                    self.assertTrue(role_docs.render_description(spec), f"{name}: no description")
                    if "choices" in spec:
                        self.assertIn(defaults[name], spec["choices"], f"{name}: default is not one of the choices")

    def test_variable_tables_are_generated(self):
        for path in role_docs.doc_files():
            with self.subTest(file=str(path.relative_to(ROOT))):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text, role_docs.render_file(text), "run: python3 tests/role_docs.py --write")

    def test_every_role_readme_and_the_configuration_page_have_a_table(self):
        configuration = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
        for role in role_docs.role_names():
            with self.subTest(role=role):
                readme = (ROOT / "roles" / role / "README.md").read_text(encoding="utf-8")
                marker = f"<!-- argument-specs:{role}:begin -->"
                self.assertIn(marker, readme)
                self.assertIn(marker, configuration)


if __name__ == "__main__":
    unittest.main()
