"""Static checks of the restic_backup role and runs of its scripts against stand-in commands.

The Molecule scenario proves the behaviour on a host with real restic; these tests catch a loosened
input pattern, a changed default, a task that could print or pass a secret on a command line, a
unit without its sandbox, an environment file that the wrapper would read differently, a backup
script that records success after a failed step, and a restore test that passes a restored copy
with a missing or changed file. The patterns are the ones assert.yml uses (Ansible's "match" test
is Python's re.match). They need PyYAML and Jinja2 (requirements-test.txt).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

try:
    import jinja2
    import yaml
except ImportError:  # pragma: no cover - only without the test requirements
    jinja2 = None
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
ROLE = ROOT / "roles" / "restic_backup"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def all_tasks(tasks: list) -> list:
    """The tasks of a task file, with the tasks inside blocks."""
    found = []
    for task in tasks:
        found.append(task)
        for key in ("block", "rescue", "always"):
            found.extend(all_tasks(task.get(key, [])))
    return found


def role_values(**overrides) -> dict:
    """The role's defaults and internal vars, with the values a test sets, resolved like Ansible."""
    values = {**load_yaml(ROLE / "defaults" / "main.yml"), **load_yaml(ROLE / "vars" / "main.yml"), **overrides}
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    for name in ("restic_backup_restic", "restic_backup_local_repository"):
        if name not in overrides:
            values[name] = env.from_string(values[name]).render(**values).strip()
    return values


def render(template: str, **overrides) -> str:
    """Render a role template the way the template module does (trim_blocks, trailing newline)."""
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROLE / "templates")), trim_blocks=True,
                             keep_trailing_newline=True, undefined=jinja2.StrictUndefined)
    env.filters["quote"] = lambda value: shlex.quote(str(value))
    env.filters["to_json"] = json.dumps
    return env.get_template(template).render(ansible_managed="Managed by Ansible", **role_values(**overrides))


@unittest.skipIf(yaml is None, "PyYAML is not installed (pip install -r requirements-test.txt)")
class ResticBackupInputPatternTest(unittest.TestCase):
    def setUp(self):
        self.vars = load_yaml(ROLE / "vars" / "main.yml")

    def check(self, name: str, good: list[str], bad: list[str]):
        pattern = re.compile(self.vars[name])
        for value in good:
            self.assertTrue(pattern.match(value), f"{name} should accept {value!r}")
        for value in bad:
            self.assertFalse(pattern.match(value), f"{name} should refuse {value!r}")

    def test_repository(self):
        self.check("restic_backup_repository_pattern",
                   ["/srv/restic-repo", "local:/srv/restic-repo", "s3:https://s3.example.com/backups/edge-01",
                    "sftp:backup@example.com:/srv/restic/edge-01", "rest:https://backup.example.com/edge-01/",
                    "b2:bucket:edge-01", "rclone:remote:edge-01"],
                   ["", "srv/restic-repo", "local:", "ftp://backup.example.com/x", "s3:https://s3.example.com/a b",
                    "/srv/repo\nExecStart=/bin/sh", "s3:", "/srv/restic-repo\n"])

    def test_paths_and_folders(self):
        self.check("restic_backup_path_pattern",
                   ["/", "/etc", "/var/backups", "/srv/molecule-data", "/opt/fxserver/server-data", "/srv/a@b+c"],
                   ["", "etc", "/etc/", "/var/../etc", "/var/./x", "/my files", "/etc\n", "//etc", "/$HOME"])
        # Folders that the role writes to or creates its folder in: never / or a system folder.
        self.check("restic_backup_dir_forbidden_pattern",
                   ["/", "/etc", "/etc/restic", "/usr/local/backups", "/run/x", "/proc/1"],
                   ["/var/tmp", "/srv/restic-repo", "/var/lib/prometheus/node-exporter", "/etcetera", "/tmp"])

    def test_environment_names(self):
        self.check("restic_backup_env_name_pattern", ["AWS_ACCESS_KEY_ID", "B2_ACCOUNT_ID", "RESTIC_COMPRESSION"],
                   ["", "aws_access_key_id", "1KEY", "KEY-ID", "KEY ID", "KEY\n"])
        # The variables that env.j2 writes itself may not come from restic_backup_env.
        self.check("restic_backup_reserved_env_pattern",
                   ["RESTIC_REPOSITORY", "RESTIC_REPOSITORY_FILE", "RESTIC_PASSWORD", "RESTIC_PASSWORD_FILE",
                    "RESTIC_PASSWORD_COMMAND", "RESTIC_CACHE_DIR"],
                   ["RESTIC_COMPRESSION", "RESTIC_PACK_SIZE", "AWS_ACCESS_KEY_ID"])
        written = re.findall(r"^([A-Z_]+)=", (ROLE / "templates" / "env.j2").read_text(encoding="utf-8"), re.MULTILINE)
        self.assertEqual(written, ["RESTIC_REPOSITORY", "RESTIC_PASSWORD_FILE", "RESTIC_CACHE_DIR"])
        reserved = re.compile(self.vars["restic_backup_reserved_env_pattern"])
        for name in written:
            self.assertTrue(reserved.match(name), name)

    def test_exclude_patterns(self):
        self.check("restic_backup_exclude_pattern", ["*.log", "/var/backups/*.tmp", "/home/*/.cache", "$$HOME", "a"],
                   ["", "#comment", " leading", "trailing ", "two\nlines", "tab\there", "*.log\n"])

    def test_versions_checksums_and_schedules(self):
        self.check("restic_backup_version_pattern", ["0.19.1", "0.18.0", "1.0.10"], ["0.19", "v0.19.1", "0.19.1-rc1", "", "0.19.1\n"])
        self.check("restic_backup_sha256_pattern", ["0" * 64, "f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c"],
                   ["0" * 63, "F" * 64, "g" * 64, ""])
        self.check("restic_backup_oncalendar_pattern", ["*-*-* 03:45:00", "monthly", "Mon..Fri 02:00", "*-*-01 05:15"],
                   ["daily\nExecStart=/bin/sh", "daily; reboot", "50%", "", "daily\n"])
        self.check("restic_backup_read_data_subset_pattern", ["", "5%", "2.5%", "100%", "1/12", "12/12"],
                   ["5", "5 %", "0/12", "1/0", "1G", "%", "5%\n"])


@unittest.skipIf(yaml is None, "PyYAML is not installed (pip install -r requirements-test.txt)")
class ResticBackupDefaultsAndSecretsTest(unittest.TestCase):
    def setUp(self):
        self.defaults = load_yaml(ROLE / "defaults" / "main.yml")
        self.vars = load_yaml(ROLE / "vars" / "main.yml")

    def test_defaults(self):
        d = self.defaults
        self.assertEqual(d["restic_backup_install_method"], "package")
        self.assertEqual(d["restic_backup_repository"], "")
        self.assertEqual(d["restic_backup_password"], "")
        self.assertEqual(d["restic_backup_env"], {})
        self.assertEqual(d["restic_backup_paths"], ["/etc", "/var/backups"])
        self.assertEqual(d["restic_backup_keep"], {"daily": 7, "weekly": 4, "monthly": 6})
        self.assertIs(d["restic_backup_timers_enabled"], True)
        self.assertEqual(d["restic_backup_check_oncalendar"], "monthly")
        self.assertEqual(d["restic_backup_textfile_dir"], "")
        self.assertEqual(d["restic_backup_max_age_hours"], 26)
        self.assertEqual(d["restic_backup_restore_test_dir"], "/var/tmp")
        self.assertRegex(d["restic_backup_version"], self.vars["restic_backup_version_pattern"])
        self.assertEqual(sorted(d["restic_backup_binary_sha256"]), sorted(self.vars["restic_backup_architectures"].values()))
        for checksum in d["restic_backup_binary_sha256"].values():
            self.assertRegex(checksum, self.vars["restic_backup_sha256_pattern"])

    def test_backup_runs_after_the_dumps_of_mariadb(self):
        """The default backup time follows the dump timer of the mariadb role, whose folder is backed up."""
        mariadb = load_yaml(ROOT / "roles" / "mariadb" / "defaults" / "main.yml")
        dump = re.fullmatch(r"\*-\*-\* (\d\d:\d\d):00", mariadb["mariadb_dump_oncalendar"]).group(1)
        backup = re.fullmatch(r"\*-\*-\* (\d\d:\d\d):00", self.defaults["restic_backup_oncalendar"]).group(1)
        self.assertLess(dump, backup)
        self.assertTrue(mariadb["mariadb_dump_dir"].startswith(self.defaults["restic_backup_paths"][1] + "/"))

    def test_every_task_that_handles_a_secret_hides_it(self):
        """Tasks that pass the password or the backend credentials need no_log (asserts only test them)."""
        seen = []
        for path in sorted((ROLE / "tasks").glob("*.yml")):
            for task in all_tasks(load_yaml(path) or []):
                if "ansible.builtin.assert" in task:
                    continue
                text = yaml.safe_dump({k: v for k, v in task.items() if k not in ("block", "rescue", "always")})
                if "restic_backup_password" in text or "restic_backup_env" in text or task.get("ansible.builtin.template", {}).get("src") == "env.j2":
                    seen.append(task["name"])
                    with self.subTest(file=path.name, task=task["name"]):
                        self.assertIs(task.get("no_log"), True)
        self.assertEqual(seen, ["Open the repository with the new settings (given on standard input, not as arguments)",
                                "Write the repository settings (/etc/restic/env)",
                                "Write the repository password (/etc/restic/password)"])

    def test_secrets_reach_restic_on_standard_input_only(self):
        repository = load_yaml(ROLE / "tasks" / "repository.yml")
        probe = next(t for t in repository if t["name"].startswith("Open the repository with the new settings"))
        argv = probe["ansible.builtin.command"]["argv"]
        self.assertNotIn("environment", probe)
        for item in argv:
            self.assertNotRegex(str(item), r"restic_backup_(password|env|repository)\b")
        stdin = probe["ansible.builtin.command"]["stdin"]
        for name in ("restic_backup_password", "restic_backup_env", "restic_backup_repository"):
            self.assertIn(name, stdin)
        for path in sorted((ROLE / "tasks").glob("*.yml")):
            for task in all_tasks(load_yaml(path) or []):
                self.assertNotIn("environment", task, f"{path.name}: {task.get('name')}")

    def test_secret_options_are_no_log(self):
        spec = load_yaml(ROLE / "meta" / "argument_specs.yml")["argument_specs"]["main"]["options"]
        self.assertIs(spec["restic_backup_password"]["no_log"], True)
        self.assertIs(spec["restic_backup_env"]["no_log"], True)
        self.assertEqual(sorted(spec["restic_backup_keep"]["options"]), ["daily", "hourly", "last", "monthly", "weekly", "yearly"])

    def test_settings_files_are_root_only(self):
        repository = {t["name"]: t for t in load_yaml(ROLE / "tasks" / "repository.yml")}
        for name in ("Write the repository settings (/etc/restic/env)", "Write the repository password (/etc/restic/password)",
                     "Write the exclude patterns (/etc/restic/excludes)"):
            module = repository[name].get("ansible.builtin.template") or repository[name]["ansible.builtin.copy"]
            self.assertEqual((module["owner"], module["group"], module["mode"]), ("root", "root", "0600"), name)
        folders = repository["Create the folders for the settings, the cache and the status"]["loop"]
        self.assertIn({"path": "{{ restic_backup_config_dir }}", "mode": "0700"}, folders)

    def test_init_only_for_a_missing_repository(self):
        init = next(t for t in load_yaml(ROLE / "tasks" / "repository.yml") if t["name"] == "Initialise the repository")
        self.assertIn("restic_backup_repository_state.state == 'missing'", init["when"])
        self.assertEqual(init["ansible.builtin.command"]["argv"], ["{{ restic_backup_wrapper }}", "init"])

    def test_units(self):
        sandbox = (ROLE / "templates" / "sandbox.j2").read_text(encoding="utf-8").splitlines()
        for line in ("NoNewPrivileges=yes", "CapabilityBoundingSet=CAP_DAC_READ_SEARCH", "ProtectSystem=strict",
                     "ProtectHome=read-only", "PrivateTmp=yes", "PrivateDevices=yes",
                     "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", "SystemCallFilter=@system-service"):
            self.assertIn(line, sandbox)
        for name in ("restic-backup.service.j2", "restic-check.service.j2"):
            text = (ROLE / "templates" / name).read_text(encoding="utf-8")
            self.assertIn("{% include 'sandbox.j2' %}", text, name)
            self.assertIn("Type=oneshot", text.splitlines(), name)
            self.assertIn("UMask=0077", text.splitlines(), name)
        backup = (ROLE / "templates" / "restic-backup.service.j2").read_text(encoding="utf-8").splitlines()
        self.assertIn("After=network-online.target mariadb-dump.service", backup)
        for name in ("restic-backup.timer.j2", "restic-check.timer.j2"):
            lines = (ROLE / "templates" / name).read_text(encoding="utf-8").splitlines()
            self.assertIn("Persistent=true", lines, name)
            self.assertIn("WantedBy=timers.target", lines, name)

    def test_rendered_units(self):
        if jinja2 is None:
            self.skipTest("Jinja2 is not installed")
        backup = render("restic-backup.service.j2", restic_backup_repository="/srv/restic-repo",
                        restic_backup_textfile_dir="/var/lib/prometheus/node-exporter")
        self.assertIn("ReadWritePaths=/var/cache/restic-backup /var/lib/restic-backup /srv/restic-repo "
                      "-/var/lib/prometheus/node-exporter\nProtectHome=read-only\n", backup)
        remote = render("restic-backup.service.j2", restic_backup_repository="s3:https://s3.example.com/b/h")
        self.assertIn("ReadWritePaths=/var/cache/restic-backup /var/lib/restic-backup\nProtectHome=read-only\n", remote)
        # systemd reads "%" as a specifier, so the data subset of the check is escaped.
        check = render("restic-check.service.j2", restic_backup_repository="/srv/restic-repo",
                       restic_backup_check_read_data_subset="5%")
        self.assertIn("ExecStart=/usr/local/sbin/restic-env --retry-lock 2h check --read-data-subset=5%%\nUser=root\n", check)
        plain = render("restic-check.service.j2", restic_backup_repository="/srv/restic-repo")
        self.assertIn("ExecStart=/usr/local/sbin/restic-env --retry-lock 2h check\nUser=root\n", plain)
        self.assertNotIn("{%", backup + check)

    def test_wrapper_uses_the_binary_of_the_method(self):
        if jinja2 is None:
            self.skipTest("Jinja2 is not installed")
        self.assertIn('\nexec /usr/bin/restic "$@"\n', render("restic-env.sh.j2"))
        self.assertIn('\nexec /usr/local/bin/restic "$@"\n', render("restic-env.sh.j2", restic_backup_install_method="binary"))
        self.assertEqual(role_values(restic_backup_repository="local:/srv/r")["restic_backup_local_repository"], "/srv/r")
        self.assertEqual(role_values(restic_backup_repository="/srv/r")["restic_backup_local_repository"], "/srv/r")
        self.assertEqual(role_values(restic_backup_repository="s3:https://s3.example.com/b")["restic_backup_local_repository"], "")


@unittest.skipIf(jinja2 is None, "Jinja2 is not installed (pip install -r requirements-test.txt)")
@unittest.skipUnless(shutil.which("bash"), "bash is needed")
class EnvironmentFileTest(unittest.TestCase):
    """The wrapper reads /etc/restic/env with bash; every value must arrive unchanged."""

    def test_values_survive_the_shell(self):
        tricky = {"AWS_SECRET_ACCESS_KEY": "a'b\"c $HOME `id` $(id) \\ ; & | * ~ #x",
                  "B2_ACCOUNT_KEY": " spaces at both ends ", "RESTIC_COMPRESSION": "max", "EMPTY_VALUE": ""}
        text = render("env.j2", restic_backup_repository="s3:https://s3.example.com/b/h?x=1&y=2",
                      restic_backup_env=tricky)
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "env"
            env_file.write_text(text, encoding="utf-8")
            names = ["RESTIC_REPOSITORY", "RESTIC_PASSWORD_FILE", "RESTIC_CACHE_DIR", *sorted(tricky)]
            script = f'set -euo pipefail; set -a; . {shlex.quote(str(env_file))}; set +a; ' + "; ".join(
                f'printf "%s\\0" "${{{name}}}"' for name in names)
            out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True, env={"PATH": os.defpath})
        values = out.stdout.split("\0")[:-1]
        self.assertEqual(values, ["s3:https://s3.example.com/b/h?x=1&y=2", "/etc/restic/password", "/var/cache/restic-backup",
                                  *[tricky[name] for name in sorted(tricky)]])


FAKE_WRAPPER = """#!/bin/bash
# Stand-in for /usr/local/sbin/restic-env: records its arguments; fails for the command in FAIL_ON.
printf '%s\\n' "$*" >> "$RESTIC_TEST_LOG"
for arg in "$@"; do
  if [ -n "${FAIL_ON:-}" ] && [ "$arg" = "$FAIL_ON" ]; then
    echo "Fatal: $FAIL_ON failed" >&2
    exit 3
  fi
done
"""


@unittest.skipIf(jinja2 is None, "Jinja2 is not installed (pip install -r requirements-test.txt)")
@unittest.skipUnless(shutil.which("bash") and shutil.which("mktemp"), "bash and mktemp are needed")
class BackupScriptTest(unittest.TestCase):
    """Render restic-backup.sh.j2 and run it with a stand-in for the wrapper."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="restic-backup-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "data" / "sub").mkdir(parents=True)
        (self.tmp / "state").mkdir()
        (self.tmp / "textfile").mkdir()
        wrapper = self.tmp / "restic-env"
        wrapper.write_text(FAKE_WRAPPER, encoding="utf-8")
        wrapper.chmod(0o755)
        self.log = self.tmp / "calls.log"
        self.status = self.tmp / "state" / "last-success"
        self.paths = [str(self.tmp / "data"), str(self.tmp / "data" / "sub")]
        self.env = {**os.environ, "RESTIC_TEST_LOG": str(self.log)}
        self.wrapper = wrapper

    def script(self, **overrides) -> Path:
        values = {"restic_backup_wrapper": str(self.wrapper), "restic_backup_paths": self.paths,
                  "restic_backup_status_file": str(self.status),
                  "restic_backup_textfile_dir": str(self.tmp / "textfile"), **overrides}
        path = self.tmp / "restic-backup"
        path.write_text(render("restic-backup.sh.j2", **values), encoding="utf-8")
        path.chmod(0o755)
        return path

    def run_script(self, script: Path, **extra_env):
        return subprocess.run(["bash", str(script)], env={**self.env, **extra_env}, capture_output=True, text=True,
                              check=False)

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def test_backup_forget_and_the_status_with_the_metric(self):
        before = int(time.time())
        result = self.run_script(self.script())
        self.assertEqual(result.returncode, 0, result.stderr)
        host = os.uname().nodename
        self.assertEqual(self.calls(), [
            f"--retry-lock 2h backup --host {host} --exclude-caches --exclude-file /etc/restic/excludes {' '.join(self.paths)}",
            f"--retry-lock 2h forget --host {host} --prune --keep-daily 7 --keep-monthly 6 --keep-weekly 4"])
        stamp = self.status.read_text(encoding="utf-8")
        self.assertRegex(stamp, r"^[0-9]{10}\n$")
        self.assertGreaterEqual(int(stamp), before)
        metric = (self.tmp / "textfile" / "restic_backup.prom").read_text(encoding="utf-8").splitlines()
        self.assertEqual(metric[1:], ["# TYPE restic_backup_last_success_timestamp_seconds gauge",
                                      f"restic_backup_last_success_timestamp_seconds {stamp.strip()}"])
        self.assertTrue(metric[0].startswith("# HELP restic_backup_last_success_timestamp_seconds "))
        for path in (self.status, self.tmp / "textfile" / "restic_backup.prom"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o644, path)
        self.assertEqual(sorted(p.name for p in (self.tmp / "state").iterdir()), ["last-success"])
        self.assertEqual(sorted(p.name for p in (self.tmp / "textfile").iterdir()), ["restic_backup.prom"])
        self.assertIn("applied the retention (--keep-daily 7 --keep-monthly 6 --keep-weekly 4)", result.stdout)

    def test_no_metric_without_a_textfile_folder(self):
        result = self.run_script(self.script(restic_backup_textfile_dir="", restic_backup_keep={"last": 1}))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.calls()[1].endswith("--prune --keep-last 1"))
        self.assertTrue(self.status.exists())
        self.assertEqual(list((self.tmp / "textfile").iterdir()), [])

    def test_a_missing_path_fails_before_restic_runs(self):
        missing = str(self.tmp / "missing")
        result = self.run_script(self.script(restic_backup_paths=[*self.paths, missing]))
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"these paths do not exist: {missing}", result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.status.exists())

    def test_a_failed_backup_or_forget_keeps_the_last_status(self):
        self.status.write_text("1000000000\n", encoding="utf-8")
        for step, expected_calls in (("backup", 1), ("forget", 2)):
            with self.subTest(step=step):
                self.log.unlink(missing_ok=True)
                result = self.run_script(self.script(), FAIL_ON=step)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.calls()), expected_calls)
                self.assertEqual(self.status.read_text(encoding="utf-8"), "1000000000\n")
                self.assertFalse((self.tmp / "textfile" / "restic_backup.prom").exists())


FAKE_RESTIC = """#!/usr/bin/env python3
# Stand-in for the wrapper: answers snapshots, ls and restore from the fixture in FAKE_RESTIC_FIXTURE.
import json, os, sys
args = sys.argv[1:]
if args[:1] == ["--retry-lock"]:
    args = args[2:]
fixture = json.load(open(os.environ["FAKE_RESTIC_FIXTURE"]))
with open(os.environ["FAKE_RESTIC_LOG"], "a") as log:
    log.write(" ".join(args) + "\\n")
if args[0] == "snapshots":
    print(json.dumps(fixture["snapshots"]))
elif args[0] == "ls":
    print(json.dumps({**fixture["snapshots"][-1], "struct_type": "snapshot"}))
    for node in fixture["nodes"]:
        print(json.dumps({**node, "struct_type": "node"}))
elif args[0] == "restore":
    if fixture.get("restore_rc"):
        print("Fatal: restore failed", file=sys.stderr)
        sys.exit(fixture["restore_rc"])
    target = args[args.index("--target") + 1]
    includes = [args[i + 1] for i, arg in enumerate(args) if arg == "--include"]
    defects = fixture.get("defects", {})
    for node in fixture["nodes"]:
        path = node["path"]
        if includes and not any(path == p or path.startswith(p + "/") for p in includes):
            continue
        if defects.get(path) == "missing":
            continue
        dest = target + path
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if node["type"] == "dir":
            os.makedirs(dest, exist_ok=True)
        elif node["type"] == "symlink":
            os.symlink("target", dest)
        elif node["type"] == "file":
            size = node.get("size", 0) + (1 if defects.get(path) == "size" else 0)
            with open(dest, "wb") as handle:
                handle.write(b"x" * size)
        else:
            continue
        if node["type"] != "symlink":
            mode = node["mode"] & 0o777
            os.chmod(dest, 0o600 if defects.get(path) == "mode" else mode)
else:
    sys.exit("unexpected command: " + " ".join(args))
"""


@unittest.skipIf(jinja2 is None, "Jinja2 is not installed (pip install -r requirements-test.txt)")
class RestoreTestScriptTest(unittest.TestCase):
    """Render restic-restore-test.py.j2 and run it against a stand-in for the wrapper."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="restic-restore-test-unit-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.restore_dir = self.tmp / "restore"
        self.restore_dir.mkdir()
        fake = self.tmp / "restic-env"
        fake.write_text(FAKE_RESTIC, encoding="utf-8")
        fake.chmod(0o755)
        self.fake = fake
        self.fixture_path = self.tmp / "fixture.json"
        self.log = self.tmp / "calls.log"
        uid, gid = os.getuid(), os.getgid()
        self.fixture = {
            "snapshots": [
                {"id": "a" * 64, "short_id": "aaaaaaaa", "time": "2000-01-01T00:00:00.5Z", "paths": ["/etc", "/srv"]},
                {"id": "b" * 64, "short_id": "bbbbbbbb", "time": self.time_ago(hours=2), "paths": ["/etc", "/srv"]}],
            "nodes": [
                {"type": "dir", "path": "/etc", "mode": (1 << 31) | 0o755, "uid": uid, "gid": gid},
                {"type": "file", "path": "/etc/hostname", "size": 8, "mode": 0o644, "uid": uid, "gid": gid},
                {"type": "symlink", "path": "/etc/localtime", "mode": 0o777, "uid": uid, "gid": gid},
                {"type": "dir", "path": "/srv", "mode": (1 << 31) | 0o750, "uid": uid, "gid": gid},
                {"type": "file", "path": "/srv/app/data.db", "size": 4096, "mode": 0o640, "uid": uid, "gid": gid},
                {"type": "file", "path": "/srv/app/empty", "mode": 0o600, "uid": uid, "gid": gid},
                {"type": "fifo", "path": "/srv/app/pipe", "mode": 0o644, "uid": uid, "gid": gid}],
        }

    @staticmethod
    def time_ago(hours: float) -> str:
        """An RFC 3339 time with nanoseconds and an offset, as restic writes it."""
        stamp = time.time() - hours * 3600
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(stamp + 7200)) + ".123456789+02:00"

    def load_script(self, **overrides):
        values = {"restic_backup_wrapper": str(self.fake), "restic_backup_restore_test_dir": str(self.restore_dir),
                  **overrides}
        path = self.tmp / "restic_restore_test.py"
        path.write_text(render("restic-restore-test.py.j2", **values), encoding="utf-8")
        spec = importlib.util.spec_from_file_location("restic_restore_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_test(self, *argv, **overrides) -> tuple[int, str, str]:
        self.fixture_path.write_text(json.dumps(self.fixture), encoding="utf-8")
        module = self.load_script(**overrides)
        out, err = io.StringIO(), io.StringIO()
        env = {"FAKE_RESTIC_FIXTURE": str(self.fixture_path), "FAKE_RESTIC_LOG": str(self.log)}
        with mock.patch.dict(os.environ, env), mock.patch.object(module, "require_root", return_value=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = module.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()

    def test_passes_for_a_complete_copy_and_removes_it(self):
        rc, out, err = self.run_test()
        self.assertEqual(rc, 0, err)
        self.assertIn("newest snapshot bbbbbbbb of host", out)
        self.assertIn("2.0 hours old (limit 26)", out)
        self.assertIn("restored 3 files (4104 bytes), 2 folders, 1 links and 1 other entries", out)
        self.assertIn("passed: every file, folder and link of the snapshot is in the restored copy", out)
        host = os.uname().nodename
        self.assertEqual(self.calls(), [f"snapshots --json --host {host}", f"ls --json {'b' * 64}",
                                        f"restore {'b' * 64} --target {self.calls()[2].split()[3]} --verify"])
        self.assertEqual(list(self.restore_dir.iterdir()), [], "the restored copy must be removed")

    def test_fails_for_a_missing_file_a_changed_size_or_mode(self):
        for defect, message in (("missing", "/srv/app/data.db: missing in the restored copy"),
                                ("size", "/srv/app/data.db: 4097 bytes instead of 4096"),
                                ("mode", "/srv/app/data.db: mode 600 instead of 640")):
            with self.subTest(defect=defect):
                self.fixture["defects"] = {"/srv/app/data.db": defect}
                rc, _, err = self.run_test()
                self.assertEqual(rc, 1)
                self.assertIn("FAILED: 1 difference(s) between the snapshot and the restored copy", err)
                self.assertIn(message, err)
                self.assertEqual(list(self.restore_dir.iterdir()), [])

    def test_fails_for_an_old_snapshot_without_restoring(self):
        self.fixture["snapshots"][-1]["time"] = self.time_ago(hours=30)
        rc, _, err = self.run_test()
        self.assertEqual(rc, 1)
        self.assertIn("FAILED: the newest snapshot is 30.0 hours old, more than 26", err)
        self.assertEqual(len(self.calls()), 1)
        rc, out, err = self.run_test("--max-age-hours", "48")
        self.assertEqual(rc, 0, err)

    def test_fails_without_snapshots_and_when_restic_fails(self):
        self.fixture["snapshots"] = []
        rc, _, err = self.run_test()
        self.assertEqual(rc, 1)
        self.assertIn("FAILED: the repository has no snapshot of host", err)
        self.setUp()
        self.fixture["restore_rc"] = 1
        rc, _, err = self.run_test()
        self.assertEqual(rc, 1)
        self.assertIn("FAILED: restic restore failed with exit code 1: Fatal: restore failed", err)
        self.assertEqual(list(self.restore_dir.iterdir()), [])

    def test_include_restores_and_compares_the_listed_paths_only(self):
        self.fixture["defects"] = {"/etc/hostname": "missing"}
        rc, out, err = self.run_test(restic_backup_restore_test_include=["/srv/app"])
        self.assertEqual(rc, 0, err)
        self.assertIn("restored 2 files (4096 bytes), 0 folders, 0 links and 1 other entries", out)
        self.assertIn("of the snapshot under /srv/app is in the restored copy", out)
        self.assertTrue(self.calls()[2].endswith("--verify --include /srv/app"))

    def test_keep_leaves_the_restored_copy(self):
        rc, out, _ = self.run_test("--keep")
        self.assertEqual(rc, 0)
        kept = list(self.restore_dir.iterdir())
        self.assertEqual(len(kept), 1)
        self.assertTrue(kept[0].name.startswith("restic-restore-test-"))
        self.assertIn(f"kept the restored copy in {kept[0]}", out)
        self.assertTrue((kept[0] / "srv" / "app" / "data.db").is_file())

    def test_refuses_to_run_without_root(self):
        module = self.load_script()
        err = io.StringIO()
        with mock.patch.object(module.os, "geteuid", return_value=1000), contextlib.redirect_stderr(err):
            self.assertEqual(module.main([]), 2)
        self.assertIn("run it as root", err.getvalue())

    def test_reads_restic_times(self):
        module = self.load_script()
        parsed = module.parse_time("2026-10-22T03:45:01.123456789+02:00")
        self.assertEqual(parsed.isoformat(), "2026-10-22T03:45:01.123456+02:00")
        self.assertEqual(module.parse_time("2026-10-22T01:45:01Z").timestamp(), parsed.timestamp() - 0.123456)
        with self.assertRaises(module.TestFailed):
            module.parse_time("22.10.2026 03:45")


FAKE_PROBE_RESTIC = """#!/usr/bin/env python3
# Stand-in for restic in repository_state.py: records its arguments and environment, then answers
# with the exit code and message of FAKE_RC and FAKE_STDERR.
import json, os, sys
with open(os.environ["FAKE_LOG"], "w") as log:
    json.dump({"argv": sys.argv[1:], "env": {k: v for k, v in os.environ.items()
                                            if k.startswith(("RESTIC_", "AWS_"))}}, log)
sys.stderr.write(os.environ.get("FAKE_STDERR", ""))
sys.exit(int(os.environ.get("FAKE_RC", "0")))
"""


class RepositoryStateTest(unittest.TestCase):
    """Run files/repository_state.py like the role does (python3 -c, settings on standard input)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="restic-probe-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fake = self.tmp / "restic"
        self.fake.write_text(FAKE_PROBE_RESTIC, encoding="utf-8")
        self.fake.chmod(0o755)
        self.log = self.tmp / "log.json"
        self.code = (ROLE / "files" / "repository_state.py").read_text(encoding="utf-8")

    def probe(self, rc: int, stderr: str = "", restic: str | None = None) -> dict:
        settings = {"restic": restic or str(self.fake), "repository": "s3:https://s3.example.com/b/h",
                    "password": "molecule-probe-only", "env": {"AWS_ACCESS_KEY_ID": "KEYID", "AWS_SECRET_ACCESS_KEY": "s3cr3t"}}
        env = {**os.environ, "FAKE_RC": str(rc), "FAKE_STDERR": stderr, "FAKE_LOG": str(self.log),
               "RESTIC_PASSWORD_FILE": "/somewhere/else", "RESTIC_REPOSITORY": "/wrong"}
        result = subprocess.run([sys.executable, "-c", self.code], input=json.dumps(settings), capture_output=True,
                                text=True, env=env, check=True)
        return json.loads(result.stdout)

    def test_states(self):
        missing_016 = ("Fatal: unable to open config file: stat /srv/r/config: no such file or directory\n"
                       "Is there a repository at the following location?\n/srv/r\n")
        for rc, stderr, state in ((0, "", "exists"), (10, "Fatal: repository does not exist", "missing"),
                                  (1, missing_016, "missing"), (12, "Fatal: wrong password or no key found", "wrong-password"),
                                  (1, "Fatal: wrong password or no key found\n", "wrong-password"),
                                  (1, "Fatal: unable to open repository: connection refused", "error"),
                                  (11, "unable to create lock in backend", "error")):
            with self.subTest(rc=rc, state=state):
                result = self.probe(rc, stderr)
                self.assertEqual((result["state"], result["rc"]), (state, rc))
                self.assertEqual(result["stderr"], stderr.strip())

    def test_secrets_go_to_the_environment_of_restic_only(self):
        self.probe(0)
        seen = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual(seen["argv"], ["--no-cache", "cat", "config"])
        self.assertEqual(seen["env"], {"RESTIC_REPOSITORY": "s3:https://s3.example.com/b/h",
                                       "RESTIC_PASSWORD": "molecule-probe-only",
                                       "AWS_ACCESS_KEY_ID": "KEYID", "AWS_SECRET_ACCESS_KEY": "s3cr3t"})

    def test_a_missing_binary_is_an_error(self):
        result = self.probe(0, restic=str(self.tmp / "missing"))
        self.assertEqual((result["state"], result["rc"]), ("error", -1))
        self.assertIn("No such file or directory", result["stderr"])


@unittest.skipIf(jinja2 is None, "Jinja2 is not installed (pip install -r requirements-test.txt)")
@unittest.skipUnless(shutil.which("bash"), "bash is needed")
class WrapperTest(unittest.TestCase):
    """Render restic-env.sh.j2 with a test settings file and a stand-in for restic."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="restic-env-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        restic = self.tmp / "restic"
        restic.write_text('#!/bin/bash\nprintf "%s\\n" "$*" "$RESTIC_REPOSITORY" "${RESTIC_PASSWORD:-unset}" "$AWS_KEY"\n',
                          encoding="utf-8")
        restic.chmod(0o755)
        env_file = self.tmp / "env"
        env_file.write_text("RESTIC_REPOSITORY='/srv/restic-repo'\nAWS_KEY='k e y'\n", encoding="utf-8")
        self.wrapper = self.tmp / "restic-env"
        self.wrapper.write_text(render("restic-env.sh.j2", restic_backup_env_file=str(env_file),
                                       restic_backup_restic=str(restic)), encoding="utf-8")
        self.wrapper.chmod(0o755)

    @unittest.skipUnless(os.geteuid() == 0, "the wrapper runs restic for root only")
    def test_reads_the_settings_and_drops_the_callers_restic_variables(self):
        env = {"PATH": os.defpath, "RESTIC_PASSWORD": "from-the-caller", "RESTIC_REPOSITORY": "/elsewhere"}
        result = subprocess.run([str(self.wrapper), "snapshots", "--json"], env=env, capture_output=True, text=True,
                                check=True)
        self.assertEqual(result.stdout.splitlines(), ["snapshots --json", "/srv/restic-repo", "unset", "k e y"])

    @unittest.skipIf(os.geteuid() == 0, "only a user other than root is refused")
    def test_refuses_other_users(self):
        result = subprocess.run([str(self.wrapper), "snapshots"], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("run it as root", result.stderr)


if __name__ == "__main__":
    unittest.main()
