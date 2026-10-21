"""Static checks of the cloudflared role that keep the token out of the unit and the docs true.

The Molecule scenario proves the behaviour on a host; these tests catch two mistakes earlier: a
version bump without checksums or without the documentation and test that name the version, and
a change that would put the tunnel token into the unit file or write it without no_log. They need
PyYAML (requirements-test.txt).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - only without the test requirements
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
ROLE = ROOT / "roles" / "cloudflared"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def iter_tasks(tasks):
    """Yield every task of a task list, including the tasks inside blocks."""
    for task in tasks or []:
        yield task
        for key in ("block", "rescue", "always"):
            yield from iter_tasks(task.get(key))


@unittest.skipIf(yaml is None, "PyYAML is not installed (pip install -r requirements-test.txt)")
class CloudflaredPinTest(unittest.TestCase):
    def setUp(self):
        self.defaults = load_yaml(ROLE / "defaults" / "main.yml")
        self.version = self.defaults["cloudflared_version"]

    def test_version_and_checksums(self):
        self.assertRegex(self.version, r"^\d{4}\.\d{1,2}\.\d+$")
        checksums = self.defaults["cloudflared_deb_sha256"]
        self.assertEqual(sorted(checksums), ["amd64", "arm64"])
        for arch, value in checksums.items():
            self.assertRegex(value, r"^[0-9a-f]{64}$", arch)
        self.assertNotEqual(checksums["amd64"], checksums["arm64"])

    def test_docs_and_scenario_name_the_pinned_version(self):
        """A version bump must also update the README rows and the version the scenario expects."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        row = next((ln for ln in readme.splitlines() if ln.startswith("| cloudflared (managed host)")), None)
        self.assertIsNotNone(row, "README.md: the supported versions table has no cloudflared row")
        self.assertIn(self.version, row)
        role_readme = (ROLE / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"`cloudflared_version` ({self.version})", role_readme)
        verify = load_yaml(ROLE / "molecule" / "default" / "verify.yml")
        self.assertEqual(verify[0]["vars"]["cloudflared_test_version"], self.version)


@unittest.skipIf(yaml is None, "PyYAML is not installed (pip install -r requirements-test.txt)")
class CloudflaredTokenTest(unittest.TestCase):
    def test_unit_reads_the_token_from_its_file(self):
        unit = (ROLE / "templates" / "cloudflared.service.j2").read_text(encoding="utf-8")
        exec_start = [ln for ln in unit.splitlines() if ln.startswith("ExecStart=")]
        self.assertEqual(len(exec_start), 1)
        self.assertIn("--no-autoupdate", exec_start[0])
        self.assertIn("--metrics {{ cloudflared_metrics_address }}", exec_start[0])
        self.assertTrue(exec_start[0].endswith(" run --token-file {{ cloudflared_token_file }}"), exec_start[0])
        self.assertNotRegex(unit, r"--token(?!-file)")
        self.assertNotRegex(unit, r"\bcloudflared_token\b(?!_file)")
        self.assertNotIn("TUNNEL_TOKEN", unit)
        self.assertIn("User={{ cloudflared_user }}", unit)

    def test_tasks_that_write_the_token_hide_it(self):
        uses = 0
        for path in sorted((ROLE / "tasks").glob("*.yml")):
            for task in iter_tasks(load_yaml(path)):
                if "block" in task:
                    continue
                text = yaml.safe_dump(task)
                if not re.search(r"\{\{\s*cloudflared_token\s*\}\}", text):
                    continue
                uses += 1
                with self.subTest(file=path.name, task=task.get("name")):
                    self.assertIs(task.get("no_log"), True)
                    self.assertIs(task.get("diff"), False)
        self.assertEqual(uses, 1, "exactly one task (the token file) should render the token")

    def test_argument_spec_hides_the_token(self):
        options = load_yaml(ROLE / "meta" / "argument_specs.yml")["argument_specs"]["main"]["options"]
        self.assertIs(options["cloudflared_token"].get("no_log"), True)


if __name__ == "__main__":
    unittest.main()
