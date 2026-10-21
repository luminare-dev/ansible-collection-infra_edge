"""Tests for the collection metadata, the release wiring and the shared Molecule configuration.

The YAML checks need PyYAML and the build test needs ansible-galaxy; both are in
requirements-test.txt, which the lint-test job and the release build install first. Without them
the affected tests are skipped.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - only without the test requirements
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
SLUG = "ansible-collection-infra_edge"
DESCRIPTION = "Ansible collection for edge hosts: base hardening, an outbound tunnel, a web server and a database"
INSTANCE_PREFIX = "ie-"
PLATFORM_NAME_RE = re.compile(r"ie-\$\{MOLECULE_ROLE:-role\}-([a-z0-9]+)")
DIGEST_FROM_RE = re.compile(r"^FROM (debian:trixie|ubuntu:24\.04)@sha256:[0-9a-f]{64}$", re.MULTILINE)

# Repository files that must never reach the installed collection, and files that must.
NOT_IN_TARBALL = (".github/", "docs/brand/", "scripts/", ".config/", "requirements-", "dist/", "version.txt",
                  "release-please-config.json", ".ansible-lint", ".forbidden-words-allow", ".gitleaks.toml")
NOT_IN_TARBALL_ANYWHERE = re.compile(
    r"(^|/)\.ansible(/|$)|^roles/[^/]+/molecule(/|$)|^tests(/|$)|(^|/)__pycache__(/|$)|\.tar\.gz$")
IN_TARBALL = ("README.md", "LICENSE", "NOTICE", "CHANGELOG.md", "meta/runtime.yml", "roles/README.md")


def load_yaml(rel: str):
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


@unittest.skipIf(yaml is None, "PyYAML is not installed (pip install -r requirements-test.txt)")
class GalaxyMetadataTest(unittest.TestCase):
    def setUp(self):
        self.galaxy = load_yaml("galaxy.yml")

    def test_identity(self):
        self.assertEqual(self.galaxy["namespace"], "luminare")
        self.assertEqual(self.galaxy["name"], "infra_edge")
        self.assertEqual(self.galaxy["readme"], "README.md")
        self.assertEqual(self.galaxy["license"], ["Apache-2.0"])
        self.assertEqual(self.galaxy["description"], DESCRIPTION)

    def test_authors_are_the_organization(self):
        self.assertEqual(self.galaxy["authors"], ["Luminare Development <oss@luminare.tech>"])

    def test_version_follows_version_txt(self):
        """release-please bumps version.txt and, through the generic updater, galaxy.yml."""
        self.assertEqual(self.galaxy["version"], (ROOT / "version.txt").read_text(encoding="utf-8").strip())
        lines = [ln for ln in (ROOT / "galaxy.yml").read_text(encoding="utf-8").splitlines()
                 if ln.startswith("version:")]
        self.assertEqual(len(lines), 1)
        self.assertIn("x-release-please-version", lines[0])

    def test_links(self):
        base = f"https://github.com/luminare-dev/{SLUG}"
        self.assertEqual(self.galaxy["repository"], base)
        self.assertEqual(self.galaxy["issues"], f"{base}/issues")
        self.assertTrue(self.galaxy["documentation"].startswith(base))
        self.assertEqual(self.galaxy["homepage"], f"https://luminare.tech/open-source/{SLUG}/")

    def test_dependencies_are_community_collections_with_ranges(self):
        for name, spec in (self.galaxy.get("dependencies") or {}).items():
            self.assertFalse(name.startswith("luminare."), f"{name}: luminare collections are soft dependencies")
            self.assertNotEqual(str(spec).strip(), "*", f"{name}: give a version range")

    def test_build_ignore_covers_repository_tooling(self):
        ignored = set(self.galaxy["build_ignore"])
        for pattern in ("docs/brand", "scripts", ".github", "dist", "tests", "*.tar.gz",
                        ".forbidden-words-allow", "requirements-*.txt", ".ansible", "roles/*/.ansible"):
            self.assertIn(pattern, ignored)

    def test_requires_ansible(self):
        runtime = load_yaml("meta/runtime.yml")
        self.assertRegex(runtime["requires_ansible"], r"^>=2\.\d+\.\d+$")


class ReleaseWiringTest(unittest.TestCase):
    def test_release_please_updates_the_versioned_files(self):
        cfg = json.loads((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
        extra = cfg["packages"]["."]["extra-files"]
        self.assertIn({"type": "generic", "path": "galaxy.yml"}, extra)
        for entry in extra:
            # The "yaml" updater rewrites the whole file and drops every comment.
            self.assertEqual(entry["type"], "generic", entry)

    def test_install_commands_use_the_released_tag(self):
        """README and docs/install.md install from a vX.Y.Z tag inside a release-please block."""
        for rel in ("README.md", "docs/install.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            block = re.search(r"x-release-please-start-version.*?x-release-please-end", text, re.DOTALL)
            self.assertIsNotNone(block, rel)
            self.assertRegex(block.group(0),
                             rf"git\+https://github\.com/luminare-dev/{SLUG}\.git,v\d+\.\d+\.\d+", rel)


@unittest.skipIf(yaml is None, "PyYAML is not installed (pip install -r requirements-test.txt)")
class MoleculeConfigTest(unittest.TestCase):
    def test_platforms(self):
        cfg = load_yaml(".config/molecule/config.yml")
        self.assertEqual(cfg["driver"]["name"], "docker")
        platforms = cfg["platforms"]
        self.assertEqual([p["image"] for p in platforms], ["ie-molecule-debian13", "ie-molecule-ubuntu2404"])
        for p in platforms:
            self.assertTrue(p["name"].startswith(INSTANCE_PREFIX), p["name"])
            self.assertTrue(p["privileged"])
            self.assertEqual(p["cgroupns_mode"], "host")
            self.assertEqual(p["volumes"], ["/sys/fs/cgroup:/sys/fs/cgroup:rw"])
            self.assertEqual(p["tmpfs"], ["/run", "/run/lock"])
            self.assertEqual(p["command"], "/lib/systemd/systemd")
            self.assertTrue((ROOT / "roles" / "role" / "molecule" / "default" / p["dockerfile"]).resolve()
                            == ROOT / ".config" / "molecule" / "Dockerfile.j2")

    def test_base_images_are_pinned_by_digest(self):
        text = (ROOT / ".config" / "molecule" / "Dockerfile.j2").read_text(encoding="utf-8")
        froms = [ln for ln in text.splitlines() if ln.startswith("FROM")]
        self.assertEqual(len(froms), 2, froms)
        self.assertEqual(len(DIGEST_FROM_RE.findall(text)), 2, froms)

    def test_role_scenarios_keep_the_instance_prefix(self):
        for scenario in sorted(ROOT.glob("roles/*/molecule/*/molecule.yml")):
            data = yaml.safe_load(scenario.read_text(encoding="utf-8")) or {}
            for p in data.get("platforms", []):
                self.assertTrue(str(p.get("name", "")).startswith(INSTANCE_PREFIX), f"{scenario}: {p}")

    def test_ci_matrix_is_role_by_platform(self):
        """ci.yml runs one job per role and platform; its platforms are exactly those of config.yml."""
        suffixes = []
        for p in load_yaml(".config/molecule/config.yml")["platforms"]:
            match = PLATFORM_NAME_RE.fullmatch(p["name"])
            self.assertIsNotNone(match, p["name"])
            suffixes.append(match.group(1))
            self.assertEqual(p["image"], f"ie-molecule-{match.group(1)}")
        job = load_yaml(".github/workflows/ci.yml")["jobs"]["molecule-scenario"]
        matrix = job["strategy"]["matrix"]
        self.assertEqual(sorted(matrix), ["platform", "role"])
        self.assertEqual(matrix["platform"], suffixes)
        self.assertEqual(job["name"], "molecule-scenario (${{ matrix.role }}, ${{ matrix.platform }})")
        step = next(s for s in job["steps"] if "molecule test" in s.get("run", ""))
        self.assertEqual(step["env"]["MOLECULE_ROLE"], "${{ matrix.role }}")
        self.assertEqual(step["env"]["PLATFORM"], "${{ matrix.platform }}")
        self.assertEqual(step["run"].strip(), 'molecule test --platform-name "ie-${MOLECULE_ROLE}-${PLATFORM}"')


class RoleLayoutTest(unittest.TestCase):
    def test_every_role_has_a_molecule_scenario(self):
        """CI tests only the roles with a scenario, so a role without one would go untested."""
        roles = [d for d in sorted((ROOT / "roles").iterdir())
                 if d.is_dir() and not d.name.startswith(".") and d.name != "__pycache__"]
        for role in roles:
            self.assertTrue((role / "molecule" / "default" / "molecule.yml").is_file(),
                            f"roles/{role.name} has no molecule/default/molecule.yml")


@unittest.skipUnless(shutil.which("ansible-galaxy"), "ansible-galaxy is not on the PATH")
class CollectionBuildTest(unittest.TestCase):
    """Build the collection like the release does and install the tarball into an empty path."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="collection-build-"))
        subprocess.run(["ansible-galaxy", "collection", "build", "--output-path", str(cls.tmp), str(ROOT)],
                       check=True, capture_output=True, text=True)
        tarballs = sorted(cls.tmp.glob("luminare-infra_edge-*.tar.gz"))
        if len(tarballs) != 1:
            raise AssertionError(f"expected one tarball, found {tarballs}")
        cls.tarball = tarballs[0]
        with tarfile.open(cls.tarball) as tar:
            cls.members = tar.getnames()
            cls.manifest = json.load(tar.extractfile("MANIFEST.json"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_manifest(self):
        info = self.manifest["collection_info"]
        version = (ROOT / "version.txt").read_text(encoding="utf-8").strip()
        self.assertEqual((info["namespace"], info["name"], info["version"]), ("luminare", "infra_edge", version))
        self.assertEqual(self.tarball.name, f"luminare-infra_edge-{version}.tar.gz")
        self.assertEqual(info["license"], ["Apache-2.0"])

    def test_contents(self):
        for rel in IN_TARBALL:
            self.assertIn(rel, self.members)
        for member in self.members:
            for prefix in NOT_IN_TARBALL:
                self.assertFalse(member.startswith(prefix), f"{member} should be excluded by build_ignore")
            self.assertIsNone(NOT_IN_TARBALL_ANYWHERE.search(member), f"{member} should be excluded by build_ignore")

    def test_installs(self):
        target = self.tmp / "installed"
        # Only the empty target counts as a collections path: a copy that an earlier Molecule run
        # left in ~/.ansible/collections would otherwise turn the install into "Nothing to do".
        env = {**os.environ, "ANSIBLE_COLLECTIONS_PATH": str(target)}
        subprocess.run(["ansible-galaxy", "collection", "install", "--no-deps", "-p", str(target), str(self.tarball)],
                       check=True, capture_output=True, text=True, env=env)
        installed = target / "ansible_collections" / "luminare" / "infra_edge"
        self.assertTrue((installed / "MANIFEST.json").is_file())
        self.assertTrue((installed / "meta" / "runtime.yml").is_file())


if __name__ == "__main__":
    unittest.main()
