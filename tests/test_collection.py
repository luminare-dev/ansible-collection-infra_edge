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
EDGE_SCENARIO = "extensions/molecule/edge"
EDGE_ROLES = ["luminare.infra_edge.base", "luminare.infra_edge.cloudflared", "luminare.infra_edge.nginx",
              "luminare.infra_edge.mariadb", "luminare.infra_edge.restic_backup"]
# Variables of the playbook itself (docs/configuration.md); every other inventory value is a role option.
EDGE_PLAYBOOK_VARS = {"edge_hosts", "edge_restic_backup_enabled"}
EDGE_SWITCH = "edge_restic_backup_enabled | default(false) | bool"
DIGEST_FROM_RE = re.compile(r"^FROM (debian:trixie|ubuntu:24\.04)@sha256:[0-9a-f]{64}$", re.MULTILINE)

# Repository files that must never reach the installed collection, and files that must.
NOT_IN_TARBALL = (".github/", "docs/brand/", "scripts/", ".config/", "requirements-", "dist/", "version.txt",
                  "release-please-config.json", ".ansible-lint", ".forbidden-words-allow", ".gitleaks.toml")
NOT_IN_TARBALL_ANYWHERE = re.compile(
    r"(^|/)\.ansible(/|$)|^roles/[^/]+/molecule(/|$)|^extensions(/|$)|^tests(/|$)|(^|/)__pycache__(/|$)"
    r"|\.tar\.gz$")
IN_TARBALL = ("README.md", "LICENSE", "NOTICE", "CHANGELOG.md", "meta/runtime.yml", "roles/README.md",
              "playbooks/edge.yml", "examples/edge/inventory.yml", "examples/edge/group_vars/edge/main.yml",
              "roles/restic_backup/files/repository_state.py")


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
                        ".forbidden-words-allow", "requirements-*.txt", ".ansible", "roles/*/.ansible",
                        "roles/*/molecule", "extensions"):
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

    def config_suffixes(self):
        return [PLATFORM_NAME_RE.fullmatch(p["name"]).group(1)
                for p in load_yaml(".config/molecule/config.yml")["platforms"]]

    def test_edge_scenario_uses_the_shared_platforms(self):
        """The edge scenario repeats the platforms of config.yml; only name, path and groups differ."""
        shared = load_yaml(".config/molecule/config.yml")["platforms"]
        scenario = load_yaml(f"{EDGE_SCENARIO}/molecule.yml")
        platforms = scenario["platforms"]
        self.assertEqual([p["name"] for p in platforms], [f"ie-edge-{s}" for s in self.config_suffixes()])
        own_keys = {"name", "dockerfile", "groups"}
        for edge, base in zip(platforms, shared, strict=True):
            self.assertEqual({k: v for k, v in edge.items() if k not in own_keys},
                             {k: v for k, v in base.items() if k not in own_keys}, edge["name"])
            self.assertEqual((ROOT / EDGE_SCENARIO / edge["dockerfile"]).resolve(),
                             ROOT / ".config" / "molecule" / "Dockerfile.j2")
            self.assertEqual(edge["groups"], ["edge"] + base["groups"])
        self.assertEqual(scenario["scenario"]["name"], "edge")

    def test_edge_scenario_reads_the_example_inventory(self):
        scenario = load_yaml(f"{EDGE_SCENARIO}/molecule.yml")
        link = scenario["provisioner"]["inventory"]["links"]["group_vars"]
        self.assertEqual((ROOT / EDGE_SCENARIO / link).resolve(), ROOT / "examples" / "edge" / "group_vars")
        converge = load_yaml(f"{EDGE_SCENARIO}/converge.yml")
        self.assertEqual(converge[-1], {"name": "Apply the playbook luminare.infra_edge.edge",
                                        "ansible.builtin.import_playbook": "luminare.infra_edge.edge"})

    def test_ci_runs_the_edge_scenario_per_platform(self):
        jobs = load_yaml(".github/workflows/ci.yml")["jobs"]
        job = jobs["molecule-edge"]
        self.assertEqual(job["strategy"]["matrix"], {"platform": self.config_suffixes()})
        self.assertEqual(job["name"], "molecule-edge (${{ matrix.platform }})")
        step = next(s for s in job["steps"] if "molecule test" in s.get("run", ""))
        self.assertNotIn("working-directory", step)
        self.assertEqual(step["env"]["PLATFORM"], "${{ matrix.platform }}")
        self.assertEqual(step["run"].strip(), 'molecule test --scenario-name edge --platform-name "ie-edge-${PLATFORM}"')
        self.assertIn("molecule-edge", jobs["molecule"]["needs"])
        self.assertIn("needs.molecule-edge.result", jobs["molecule"]["steps"][0]["env"]["EDGE"])


@unittest.skipIf(yaml is None, "PyYAML is not installed (pip install -r requirements-test.txt)")
class EdgePlaybookTest(unittest.TestCase):
    """playbooks/edge.yml composes the roles; examples/edge/ is its complete example inventory."""

    def role_options(self):
        options = {}
        for spec in sorted(ROOT.glob("roles/*/meta/argument_specs.yml")):
            options.update(yaml.safe_load(spec.read_text(encoding="utf-8"))["argument_specs"]["main"]["options"])
        return options

    def test_play_runs_the_roles_in_order(self):
        """The four roles always run; restic_backup only with its switch, which is off by default."""
        plays = load_yaml("playbooks/edge.yml")
        self.assertEqual(len(plays), 1)
        play = plays[0]
        self.assertEqual(play["hosts"], "{{ edge_hosts | default('edge') }}")
        self.assertIs(play["become"], True)
        self.assertEqual([r["role"] for r in play["roles"]], EDGE_ROLES)
        self.assertEqual([r.get("when") for r in play["roles"]], [None, None, None, None, EDGE_SWITCH])
        for role in play["roles"]:
            self.assertEqual(sorted(role), sorted({"role", "when"} & set(role)), role)
        self.assertNotIn("vars", play, "values belong in the inventory, not in the playbook")

    def test_example_inventory_has_one_edge_host(self):
        inventory = load_yaml("examples/edge/inventory.yml")
        hosts = inventory["all"]["children"]["edge"]["hosts"]
        self.assertEqual(list(hosts), ["edge-01.example.com"])
        for name in hosts["edge-01.example.com"]:
            self.assertTrue(name.startswith("ansible_") or name in self.role_options(), name)
        self.assertTrue(hosts["edge-01.example.com"]["restic_backup_repository"].startswith("s3:https://s3.example.com/"))

    def test_example_group_vars_are_role_variables(self):
        """A typo in the example would silently fall back to a default; every key must be a role option."""
        group_vars = load_yaml("examples/edge/group_vars/edge/main.yml")
        options = self.role_options()
        for name in group_vars:
            self.assertTrue(name in options or name in EDGE_PLAYBOOK_VARS,
                            f"{name} is not a variable of the playbook or of its roles")
        self.assertIs(group_vars["edge_restic_backup_enabled"], True)

    def test_example_keeps_secrets_out(self):
        """Secrets of the example come from the vault file or the environment, never as values."""
        group_vars = load_yaml("examples/edge/group_vars/edge/main.yml")
        self.assertNotIn("cloudflared_token", group_vars, "the token comes from TUNNEL_TOKEN")
        self.assertEqual(group_vars["base_admin_password_hash"], "{{ vault_base_admin_password_hash }}")
        for item in group_vars["mariadb_databases"]:
            self.assertRegex(item["password"], r"^\{\{ vault_[a-z_]+ \}\}$")
        self.assertRegex(group_vars["restic_backup_password"], r"^\{\{ vault_[a-z0-9_]+ \}\}$")
        for value in group_vars["restic_backup_env"].values():
            self.assertRegex(value, r"^\{\{ vault_[a-z0-9_]+ \}\}$")


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
