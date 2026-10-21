"""Static checks of the mariadb role and a run of its dump script against stand-in commands.

The Molecule scenario proves the behaviour on a host; these tests catch a loosened input pattern,
a changed default, a task that could print a password, or a dump script that deletes old dumps
after a failed run, before a scenario runs. The patterns are the ones assert.yml uses (Ansible's
"match" test is Python's re.match). They need PyYAML and Jinja2 (requirements-test.txt).
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

try:
    import jinja2
    import yaml
except ImportError:  # pragma: no cover - only without the test requirements
    jinja2 = None
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
ROLE = ROOT / "roles" / "mariadb"
STAMP = r"[0-9]{8}T[0-9]{6}Z"


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


@unittest.skipIf(yaml is None, "PyYAML is not installed (pip install -r requirements-test.txt)")
class MariadbInputPatternTest(unittest.TestCase):
    def setUp(self):
        self.vars = load_yaml(ROLE / "vars" / "main.yml")

    def check(self, name: str, good: list[str], bad: list[str]):
        pattern = re.compile(self.vars[name])
        for value in good:
            self.assertTrue(pattern.match(value), f"{name} should accept {value!r}")
        for value in bad:
            self.assertFalse(pattern.match(value), f"{name} should refuse {value!r}")

    def test_database_and_account_names(self):
        self.check("mariadb_database_name_pattern", ["app", "molecule_archive", "App2"],
                   ["app-db", "app db", "app;", "`app`", "a" * 65, ""])
        self.check("mariadb_user_name_pattern", ["app", "app.reader", "app-rw"],
                   ["app user", "app'", "app@host", ""])
        self.check("mariadb_user_host_pattern",
                   ["localhost", "192.0.2.13", "192.0.2.%", "app.example.com", "2001:db8::13",
                    "192.0.2.0/255.255.255.0"],
                   ["host name", "host'", "192.0.2.13;", ""])

    def test_addresses(self):
        self.check("mariadb_address_pattern", ["127.0.0.1", "192.0.2.10", "::1", "2001:db8::10", "0.0.0.0"],
                   ["localhost", "192.0.2.10:3306", "192.0.2.0/24", "127.0.0.1\nskip-grant-tables", ""])
        self.check("mariadb_cidr_pattern", ["192.0.2.13", "198.51.100.0/24", "2001:db8::/32", "::1"],
                   ["192.0.2.13;", "app.example.com", "198.51.100.0/24 1", "192.0.2.13:3306", ""])

    def test_sizes_names_paths_and_calendar(self):
        self.check("mariadb_size_pattern", ["256M", "1G", "1024", "512k"], ["0", "256 M", "256MB", "-1", ""])
        self.check("mariadb_charset_pattern", ["utf8mb4", "latin1", "utf8mb4_general_ci"],
                   ["utf8mb4\ninit-file=/tmp/x", "UTF8", ""])
        self.check("mariadb_path_pattern", ["/var/backups/mariadb", "/srv/db_dumps"],
                   ["var/backups", "/var/../etc", "/var/backups/", "/var/back ups", "/", "/var/./x"])
        self.check("mariadb_oncalendar_pattern", ["*-*-* 03:15:00", "daily", "Mon..Fri 02:00"],
                   ["daily\nExecStart=/bin/sh", "daily; reboot", ""])
        # The dump folder becomes root's with mode 0700: never a system folder or the data folder.
        self.check("mariadb_dump_dir_forbidden_pattern",
                   ["/etc/mysql", "/usr/local/backups", "/var/lib/mysql", "/var/lib/mysql/dumps", "/run/x"],
                   ["/var/backups/mariadb", "/srv/db_dumps", "/var/lib/mysql-dumps", "/etcetera/x"])


@unittest.skipIf(yaml is None, "PyYAML is not installed (pip install -r requirements-test.txt)")
class MariadbDefaultsAndSecretsTest(unittest.TestCase):
    def setUp(self):
        self.defaults = load_yaml(ROLE / "defaults" / "main.yml")

    def test_defaults(self):
        self.assertEqual(self.defaults["mariadb_bind_address"], "127.0.0.1")
        self.assertEqual(self.defaults["mariadb_packages"], ["mariadb-server", "python3-pymysql", "zstd"])
        self.assertEqual(self.defaults["mariadb_databases"], [])
        self.assertEqual(self.defaults["mariadb_character_set_server"], "utf8mb4")
        self.assertEqual(self.defaults["mariadb_dump_dir"], "/var/backups/mariadb")
        self.assertEqual(self.defaults["mariadb_dump_oncalendar"], "*-*-* 03:15:00")
        self.assertEqual(self.defaults["mariadb_dump_retention_days"], 2)
        self.assertIs(self.defaults["mariadb_dump_enabled"], True)
        # CONTRACT: a drop-in role writes its file only where /etc/nftables.d exists, unless told to.
        self.assertIs(self.defaults["mariadb_firewall_manage"], False)
        self.assertEqual(self.defaults["mariadb_allowed_app_hosts"], [])

    def test_every_task_that_sets_a_password_hides_it(self):
        """Tasks that pass a password to a module need no_log (the checks in assert.yml only test it)."""
        seen = []
        for path in sorted((ROLE / "tasks").glob("*.yml")):
            for task in all_tasks(load_yaml(path) or []):
                if "ansible.builtin.assert" in task:
                    continue
                text = yaml.safe_dump({k: v for k, v in task.items() if k not in ("block", "rescue", "always")})
                if "password" in text:
                    seen.append(task["name"])
                    with self.subTest(file=path.name, task=task["name"]):
                        self.assertIs(task.get("no_log"), True)
        self.assertEqual(seen, ["Create the accounts and set their passwords and privileges"])

    def test_password_option_is_no_log(self):
        spec = load_yaml(ROLE / "meta" / "argument_specs.yml")["argument_specs"]["main"]["options"]
        self.assertIs(spec["mariadb_databases"]["options"]["password"]["no_log"], True)

    def test_modules_log_in_as_root_over_the_socket(self):
        """No password for root anywhere: every ansible.mariadb task uses the socket and no ~/.my.cnf."""
        socket = load_yaml(ROLE / "vars" / "main.yml")["mariadb_socket"]
        self.assertEqual(socket, "/run/mysqld/mysqld.sock")
        count = 0
        for path in sorted((ROLE / "tasks").glob("*.yml")):
            for task in all_tasks(load_yaml(path) or []):
                for module, args in task.items():
                    if module.startswith("ansible.mariadb."):
                        count += 1
                        with self.subTest(file=path.name, task=task.get("name")):
                            self.assertEqual(args["login_unix_socket"], "{{ mariadb_socket }}")
                            self.assertEqual(args["login_user"], "root")
                            self.assertEqual(args["config_file"], "")
                            self.assertNotIn("login_password", args)
        self.assertGreaterEqual(count, 6)

    def test_root_is_kept_for_localhost_only(self):
        secure = load_yaml(ROLE / "tasks" / "secure.yml")
        remove_root = next(t for t in secure if t["name"].startswith("Remove root accounts"))
        self.assertIn("reject('equalto', 'localhost')", remove_root["loop"])
        self.assertEqual(remove_root["ansible.mariadb.mariadb_user"]["state"], "absent")

    def test_firewall_dropin_only_accepts(self):
        """The base role's convention: number 30, only "add rule inet filter input ... accept" lines."""
        self.assertEqual(load_yaml(ROLE / "vars" / "main.yml")["mariadb_firewall_dropin"],
                         "/etc/nftables.d/30-mariadb.nft")
        text = (ROLE / "templates" / "30-mariadb.nft.j2").read_text(encoding="utf-8")
        rules = [ln for ln in text.splitlines() if ln and not ln.lstrip().startswith(("#", "{%"))]
        self.assertEqual(len(rules), 2)
        for line in rules:
            self.assertTrue(line.startswith("add rule inet filter input "), line)
            self.assertIn(" tcp dport {{ mariadb_port }} accept comment ", line)
            self.assertNotRegex(line, r"\b(drop|reject|policy|flush)\b")

    def test_dump_units(self):
        service = (ROLE / "templates" / "mariadb-dump.service.j2").read_text(encoding="utf-8")
        for line in ("Type=oneshot", "UMask=0077", "ProtectSystem=strict", "ReadWritePaths={{ mariadb_dump_dir }}",
                     "PrivateNetwork=yes", "RestrictAddressFamilies=AF_UNIX", "CapabilityBoundingSet=",
                     "NoNewPrivileges=yes"):
            self.assertIn(line, service.splitlines())
        timer = (ROLE / "templates" / "mariadb-dump.timer.j2").read_text(encoding="utf-8")
        for line in ("OnCalendar={{ mariadb_dump_oncalendar }}", "Persistent=true", "WantedBy=timers.target"):
            self.assertIn(line, timer.splitlines())


FAKE_MARIADB = """#!/bin/bash
# Stand-in for the mariadb client: the database list of a server with two own databases.
printf '%s\\n' information_schema mysql performance_schema sys app 'odd-name'
"""

FAKE_DUMP = """#!/bin/bash
# Stand-in for mariadb-dump: prints its arguments; fails for the database in FAIL_DB.
for arg in "$@"; do
  if [ -n "${FAIL_DB:-}" ] && [ "$arg" = "$FAIL_DB" ]; then
    echo "mariadb-dump: Got error: 1049: Unknown database" >&2
    exit 2
  fi
done
echo "-- dump $*"
"""

FAKE_ZSTD = """#!/bin/bash
# Stand-in for zstd --quiet --stdout: copies its input.
cat
"""


@unittest.skipIf(jinja2 is None, "Jinja2 is not installed (pip install -r requirements-test.txt)")
@unittest.skipUnless(shutil.which("bash") and shutil.which("find") and shutil.which("touch"),
                     "bash, find and touch are needed")
class DumpScriptTest(unittest.TestCase):
    """Render mariadb-dump-all.sh.j2 and run it with stand-ins for mariadb, mariadb-dump and zstd."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mariadb-dump-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dump_dir = self.tmp / "dumps"
        self.dump_dir.mkdir(mode=0o700)
        bindir = self.tmp / "bin"
        bindir.mkdir()
        for name, body in (("mariadb", FAKE_MARIADB), ("mariadb-dump", FAKE_DUMP), ("zstd", FAKE_ZSTD)):
            path = bindir / name
            path.write_text(body, encoding="utf-8")
            path.chmod(0o755)
        defaults = load_yaml(ROLE / "defaults" / "main.yml")
        role_vars = load_yaml(ROLE / "vars" / "main.yml")
        env = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
        env.filters["quote"] = shlex.quote
        template = env.from_string((ROLE / "templates" / "mariadb-dump-all.sh.j2").read_text(encoding="utf-8"))
        script = template.render(ansible_managed="Managed by Ansible", **{
            **defaults, **role_vars, "mariadb_dump_dir": str(self.dump_dir)})
        self.script = self.tmp / "mariadb-dump-all"
        self.script.write_text(script, encoding="utf-8")
        self.script.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}
        # Dumps of earlier runs: one older than the 2-day retention, one from yesterday, an
        # unfinished one from three days ago, and a file that is not a dump.
        now = time.time()
        for name, age_days in (("app-20000101T000000Z.sql.zst", 3), ("app-20000102T000000Z.sql.zst", 1),
                               ("app-20000101T000001Z.sql.zst.partial", 3), ("notes.txt", 3)):
            path = self.dump_dir / name
            path.write_text("old\n", encoding="utf-8")
            os.utime(path, (now - age_days * 86400, now - age_days * 86400))

    def run_script(self, **extra_env):
        return subprocess.run(["bash", str(self.script)], env={**self.env, **extra_env},
                              capture_output=True, text=True, check=False)

    def names(self) -> list[str]:
        return sorted(p.name for p in self.dump_dir.iterdir())

    def test_one_file_per_database_plus_accounts_then_retention(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dumped 2 database(s) and the accounts", result.stdout)
        new = [n for n in self.names() if not n.startswith(("app-2000", "notes"))]
        self.assertEqual([re.sub(STAMP, "STAMP", n) for n in new],
                         ["app-STAMP.sql.zst", "odd_name-STAMP.sql.zst", "system-users-STAMP.sql.zst"])
        for name in new:
            path = self.dump_dir / name
            self.assertEqual(path.stat().st_mode & 0o777, 0o600, name)
        app = (self.dump_dir / new[0]).read_text(encoding="utf-8")
        self.assertIn("--single-transaction --routines --events --triggers --databases app", app)
        self.assertIn("--databases odd-name", (self.dump_dir / new[1]).read_text(encoding="utf-8"))
        self.assertIn("--system=users --insert-ignore", (self.dump_dir / new[2]).read_text(encoding="utf-8"))
        # Retention: the 3-day-old dump and partial file are gone, yesterday's dump and the
        # unrelated file stay; no system database was dumped.
        self.assertNotIn("app-20000101T000000Z.sql.zst", self.names())
        self.assertNotIn("app-20000101T000001Z.sql.zst.partial", self.names())
        self.assertIn("app-20000102T000000Z.sql.zst", self.names())
        self.assertIn("notes.txt", self.names())
        for system in ("information_schema", "mysql", "performance_schema", "sys"):
            self.assertFalse([n for n in self.names() if n.startswith(system + "-")], system)

    def test_a_failed_dump_keeps_the_old_files_and_leaves_no_partial_file(self):
        result = self.run_script(FAIL_DB="odd-name")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown database", result.stderr)
        self.assertIn("app-20000101T000000Z.sql.zst", self.names())
        self.assertFalse([n for n in self.names() if n.endswith(".partial") and "20000101" not in n], self.names())
        self.assertFalse([n for n in self.names() if n.startswith(("odd_name-", "system-users-"))], self.names())


if __name__ == "__main__":
    unittest.main()
