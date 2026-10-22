# luminare.infra_edge.restic_backup

Encrypted backups for a Debian 13 or Ubuntu 24.04 edge host with [restic](https://restic.net/):
every night a sandboxed systemd service backs up a list of paths (by default `/etc` and
`/var/backups`, which holds the dumps of the [`mariadb`](../mariadb/README.md) role) to a restic
repository off the host, then thins out the snapshots of the host with `forget --prune`. Once a
month a second service checks the repository. Each successful run records its time in a status
file and, optionally, as a metric for the node_exporter textfile collector, and a restore test
restores the newest snapshot into a temporary folder and compares it with the snapshot. restic
comes from the distribution or, optionally, as a pinned upstream release checked against its
SHA-256 ([ADR 0018](../../docs/adr/0018-restic-from-the-distribution-with-an-optional-pinned-release.md)).
The repository, its password and the backend credentials live in files that only root can read
([ADR 0019](../../docs/adr/0019-repository-settings-in-root-only-files-checked-before-they-change.md)).

## Requirements

- Managed host: Debian 13 or Ubuntu 24.04 (x86_64 or aarch64) with systemd and Python 3, reached
  as root or with `become: true`. The role stops before any change on another distribution.
- The distribution's package mirror (`restic` from Debian's `main` or Ubuntu's `universe`), or
  for `restic_backup_install_method: binary` the GitHub release download of restic.
- A restic repository for the host: a bucket or path on an S3-compatible service, an SFTP or REST
  server, or another restic backend, reachable from the host. The role creates the repository if
  it does not exist yet. A local path works too, but is no off-host backup.
- The repository password and the backend credentials from an encrypted source (Ansible Vault or
  a SOPS-encrypted vars file). Keep a copy of the password outside the host and the repository:
  without it the snapshots cannot be read.
- Control node: ansible-core 2.20 or later and `community.general` 13.x (a dependency of this
  collection; it decompresses the upstream release).

## Example playbook

```yaml
- name: Back up the edge host every night
  hosts: edge
  become: true
  roles:
    - role: luminare.infra_edge.restic_backup
      vars:
        restic_backup_repository: s3:https://s3.example.com/edge-backups/edge-01
        restic_backup_password: "{{ vault_backup_password }}"
        restic_backup_env:
          AWS_ACCESS_KEY_ID: "{{ vault_backup_s3_key_id }}"
          AWS_SECRET_ACCESS_KEY: "{{ vault_backup_s3_secret }}"
        restic_backup_textfile_dir: /var/lib/prometheus/node-exporter
```

The playbook [`luminare.infra_edge.edge`](../../playbooks/edge.yml) runs the role after the other
roles when `edge_restic_backup_enabled` is true, as in the
[example inventory](../../examples/edge/README.md).

## What the role does

| Control | How | Checked in Molecule |
|---|---|---|
| restic from a trusted source | `restic_backup_install_method: package` (default) installs the distribution's package without its recommended packages: restic 0.18 on Debian 13, 0.16 on Ubuntu 24.04, with the distribution's security updates; `binary` downloads the release file of `restic_backup_version` (0.19.1) from GitHub, checks its SHA-256 against `restic_backup_binary_sha256` (taken from the signed `SHA256SUMS` of the release) and installs `/usr/local/bin/restic`; a second run downloads nothing while that version is installed | the package's restic runs (0.18.0 and 0.16.4); after the switch to `binary`, `/usr/local/bin/restic` is 0.19.1 (root, 0755), the download is removed, and every job uses it |
| Secrets in root-only files | `/etc/restic` (0700) holds `env` (repository, password file, cache folder and `restic_backup_env`, every value shell-quoted), `password` and `excludes`, each root-owned with mode 0600; the tasks that write them have `no_log` and no diff, and the password and `restic_backup_env` are `no_log` options. Every restic run, also by hand, goes through `/usr/local/sbin/restic-env`, which reads `env` as root, so no secret is ever on a command line, in a unit file or in the environment of an Ansible task | owners and modes; a value with a quote, a dollar sign, backquotes, a backslash and spaces arrives unchanged; the password appears nowhere in the journal of the instance |
| New settings checked before they replace the old ones | the role opens the repository with the new settings first: they reach restic on standard input of a small helper and as environment variables of the restic process, never as arguments. A wrong password or a backend error stops the role before the settings files under `/etc/restic` change, so a working backup keeps running | a run with a wrong password stops with its message; the settings files, the repository's configuration and its keys are unchanged |
| Repository created only when missing | `restic init` runs only when restic reports that no repository exists (exit code 10 on restic 0.17 and later, the "Is there a repository" message on 0.16); restic itself refuses to initialise a location that holds a repository | the first converge creates the local repository (version 2); the second run and the run with the wrong password create nothing |
| Nightly backup with retention | `restic-backup.timer` (03:45, after the dumps of `mariadb` at 03:15, `Persistent=true`) starts `restic-backup.service`, which runs `/usr/local/sbin/restic-backup`: it fails if a path is missing (restic 0.16 to 0.18 would skip it silently), backs up the paths with `--exclude-caches` and the exclude file, then runs `forget --prune` with `restic_backup_keep` on the snapshots of this host only (`--host`); any failure stops the run before the status is written. The service is ordered after `mariadb-dump.service` when both start together | a run of the service writes a snapshot of the host with the paths, without the excluded file and the content of the cache folder, with a file of another user (mode 0600); with `keep: {last: 1}` a second run removes the first snapshot, and prune frees the space of a deleted 4 MiB file; the `edge` scenario checks the order and the default policy |
| Sandboxed jobs | both services run as root with `CapabilityBoundingSet` limited to `CAP_DAC_READ_SEARCH` (read every file, change none of other users), `ProtectSystem=strict` with write access only to the cache, the status folder, a local repository and the textfile folder, `ProtectHome=read-only`, private `/tmp` and `/dev`, network over IP and Unix sockets only, `NoNewPrivileges` and a system call filter | the unit properties; `systemd-analyze security` rates both services 2.3 |
| Monthly check | `restic-check.timer` (`monthly`, `Persistent=true`) starts `restic-check.service`: `restic check`, with `--read-data-subset` when `restic_backup_check_read_data_subset` is set; it waits for a running backup (`--retry-lock 2h`, `After=restic-backup.service`) | the check with `100%` reads all data and finds no errors |
| Status and metric | each successful run writes its Unix time to `/var/lib/restic-backup/last-success` and, with `restic_backup_textfile_dir`, `restic_backup.prom` with `restic_backup_last_success_timestamp_seconds` to that folder (both 0644, written to a temporary file and renamed) | both files hold the time of the run; the role created the missing textfile folder; no temporary file stays |
| Restore test | `/usr/local/sbin/restic-restore-test` finds the newest snapshot of the host, fails when it is older than `restic_backup_max_age_hours` (26), restores it (or `restic_backup_restore_test_include`) into a new folder in `/var/tmp` with `restic restore --verify`, compares every file, folder and link with the snapshot listing (type, size, permissions, owner), prints how long the restore took and removes the folder (see [Restore test](#restore-test)) | the test passes with both restic versions of the scenario, fails with an age limit of 0 hours, and leaves no folder behind |
| Checked before any change | paths, the repository, the names of `restic_backup_env`, exclude patterns, the retention, the folders and the timer expressions must match strict patterns (they end up in scripts, unit files and the environment file); `systemd-analyze calendar` checks both expressions; a local repository may not be inside a backed-up path | the role's own runs; the patterns also have unit tests |

## Variables

The table is generated from [`meta/argument_specs.yml`](meta/argument_specs.yml), which Ansible
also uses to check the variables when the role starts, including the kinds in
`restic_backup_keep`.

<!-- argument-specs:restic_backup:begin -->
| Variable | Type | Default | Description |
|---|---|---|---|
| `restic_backup_install_method` | str: `package`, `binary` | `package` | package installs the distribution's restic (0.18 on Debian 13, 0.16 on Ubuntu 24.04, with the distribution's security updates); binary installs the upstream release restic_backup_version as /usr/local/bin/restic after checking its SHA-256 (restic_backup_binary_sha256). An installed package stays installed with binary; the jobs use the binary of the chosen method. |
| `restic_backup_version` | str | `0.19.1` | Upstream release for restic_backup_install_method binary (x.y.z). Change it together with restic_backup_binary_sha256. |
| `restic_backup_binary_sha256` | dict | `{"amd64": "f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c", "arm64": "a5f64aaab53d51e311fa3829124c5b703f2d14cf187d8640b6be3b2b49376465"}` | SHA-256 of the release file per architecture (amd64, arm64; for example `restic_0.19.1_linux_amd64.bz2`), as listed in the signed SHA256SUMS file of the release. Used only with the binary method; the role stops on a host whose architecture has no entry, and when the downloaded file does not match. |
| `restic_backup_repository` | str | `""` | Required. The restic repository of this host, for example `s3:https://s3.example.com/backups/edge-01`, `sftp:backup@example.com:/srv/restic/edge-01`, `rest:https://backup.example.com/edge-01/` or a local path such as `/srv/restic-repo` (a local path is for tests or a second disk, not an off-host backup). Give every host its own repository. |
| `restic_backup_password` | str | `""` | Required. Password of the repository, written to /etc/restic/password (root only). Without it the snapshots cannot be read: keep a copy outside the host and the repository. Keep it encrypted (Ansible Vault, SOPS); no line break and no spaces at either end. |
| `restic_backup_env` | dict | `{}` | Environment variables for the backend, written to /etc/restic/env (root only), for example AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY for an S3 bucket. Names in capitals; not the `RESTIC_REPOSITORY*`, `RESTIC_PASSWORD*` and `RESTIC_CACHE_DIR` variables, which the role sets itself. Keep the values encrypted (Ansible Vault, SOPS). |
| `restic_backup_paths` | list of str | `["/etc", "/var/backups"]` | Absolute paths to back up (the default includes /var/backups/mariadb, the dumps of the mariadb role). Every path must exist when the backup runs: a missing path fails the run instead of being skipped. Folders tagged as caches (CACHEDIR.TAG) are left out. |
| `restic_backup_exclude` | list of str | `[]` | restic exclude patterns, one per line of /etc/restic/excludes, for example `/var/backups/*.tmp` or `*.log`. restic replaces `$NAME` with the environment variable NAME; write `$$` for a dollar sign. |
| `restic_backup_keep` | dict | `{"daily": 7, "weekly": 4, "monthly": 6}` | Retention of restic forget --prune after every backup, applied to the snapshots of this host only: how many of the newest snapshots to keep per kind (last, hourly, daily, weekly, monthly, yearly; at least one kind). The default keeps one snapshot per day for 7 days, per week for 4 weeks and per month for 6 months. |
| `restic_backup_timers_enabled` | bool | `true` | Run the backup and check timers. False stops and disables both; the services stay, so a backup can still be started by hand, and the repository is kept. |
| `restic_backup_oncalendar` | str | `*-*-* 03:45:00` | When the backup runs (systemd OnCalendar expression, local time of the host); the default follows the dumps of the mariadb role at 03:15. A run missed while the host was off follows at the next boot. |
| `restic_backup_check_oncalendar` | str | `monthly` | When restic check runs (systemd OnCalendar expression; monthly is the first day of each month at 00:00). A run missed while the host was off follows at the next boot. |
| `restic_backup_check_read_data_subset` | str | `""` | Part of the stored data that the monthly check also reads and verifies (restic check --read-data-subset), as a percentage (for example 5%, a random part on each run) or a part n/t (for example 1/12). Empty checks the structure of the repository without reading the data. |
| `restic_backup_textfile_dir` | str | `""` | Folder of the node_exporter textfile collector (for example /var/lib/prometheus/node-exporter of Debian's prometheus-node-exporter package). When set, every successful run writes restic_backup.prom with the metric restic_backup_last_success_timestamp_seconds there; the role creates the folder if it is missing. Empty writes no metric. |
| `restic_backup_max_age_hours` | int | `26` | The restore test fails when the newest snapshot of the host is older than this many hours. The default allows one nightly run plus two hours; an alert on the metric can use the same limit. |
| `restic_backup_restore_test_include` | list of str | `[]` | Paths that the restore test restores and compares, each inside one of restic_backup_paths. Empty restores the whole snapshot, which needs that much free space in restic_backup_restore_test_dir. |
| `restic_backup_restore_test_dir` | str | `/var/tmp` | Existing folder in which the restore test creates its temporary folder (mode 0700); the folder is removed after the test. |
<!-- argument-specs:restic_backup:end -->

## Tags

`restic_backup` (every task) and one tag per part: `restic_backup_install`,
`restic_backup_repository`, `restic_backup_jobs`. The checks at the start always run.

## Files and commands on the host

| Path | What it is |
|---|---|
| `/etc/restic/env`, `/etc/restic/password`, `/etc/restic/excludes` | the settings (root only, 0600) |
| `/usr/local/sbin/restic-env` | restic with the settings of this host, for example `restic-env snapshots` |
| `/usr/local/sbin/restic-backup` | the nightly backup (run it with `systemctl start restic-backup.service`) |
| `/usr/local/sbin/restic-restore-test` | the restore test |
| `restic-backup.service` / `.timer`, `restic-check.service` / `.timer` | the jobs in `/etc/systemd/system` |
| `/var/cache/restic-backup` | restic's cache (0700) |
| `/var/lib/restic-backup/last-success` | Unix time of the last run without errors |

Run a backup by hand and look at the result:

```bash
systemctl start restic-backup.service
journalctl -u restic-backup.service -n 20
restic-env snapshots
date -d @"$(cat /var/lib/restic-backup/last-success)"
```

Restore single files or a folder in place, or into another folder first:

```bash
restic-env restore latest --target / --include /etc/nginx/sites-available/app
restic-env restore latest --target /var/tmp/restore --include /var/backups/mariadb
```

`latest` means the newest snapshot of any host in the repository; with one repository per host
that is this host's. A database comes back from its dump as described in the
[mariadb role](../mariadb/README.md#dumps).

## Restore test

```bash
restic-restore-test                     # as root on the host
ansible edge --become -m ansible.builtin.command -a /usr/local/sbin/restic-restore-test
```

It prints the newest snapshot of the host, the number of files, folders and links it restored
with the bytes and the time the restore took (a measure for the time to restore the host), and
`passed`, or `FAILED` with the reason and exit code 1. `--max-age-hours <hours>` changes the age
limit for one run, `--keep` keeps the restored copy and prints its folder. The listing of restic
has no link targets, so links are checked for their type only; device files and other special
files are counted but not compared. The test restores the whole snapshot unless
`restic_backup_restore_test_include` lists paths, so `restic_backup_restore_test_dir` needs that
much free space.

## Monitoring

With `restic_backup_textfile_dir` set to the folder of node_exporter's textfile collector, the
metric `restic_backup_last_success_timestamp_seconds` shows the time of the last run without
errors. An alert that fires when no backup succeeded for longer than the restore test's limit
(26 hours):

```promql
time() - restic_backup_last_success_timestamp_seconds > 26 * 3600
```

Without node_exporter, `/var/lib/restic-backup/last-success` holds the same time, and a failed
run shows in `systemctl --failed` and `journalctl -u restic-backup.service`.

## Repository backends

The role writes `restic_backup_repository` and `restic_backup_env` as given; restic's
[documentation](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html) lists the
backends and their variables. Examples (none of them is tested here, see
[Limitations](#limitations)):

```yaml
# An S3-compatible bucket
restic_backup_repository: s3:https://s3.example.com/edge-backups/edge-01
restic_backup_env:
  AWS_ACCESS_KEY_ID: "{{ vault_backup_s3_key_id }}"
  AWS_SECRET_ACCESS_KEY: "{{ vault_backup_s3_secret }}"

# An SFTP server: the key and the server's host key must be in /root/.ssh first
# (the service reads /root read-only and cannot ask about an unknown host key).
restic_backup_repository: sftp:backup@example.com:/srv/restic/edge-01

# A REST server (rest-server); the password in the address is kept in /etc/restic/env.
restic_backup_repository: "rest:https://edge-01:{{ vault_backup_rest_password }}@backup.example.com/edge-01/"
```

Give every host its own repository: `forget` only touches the snapshots of its own host, but
the monthly check and prune of one host lock the whole repository for the others.

## Upgrading restic (binary method)

Set `restic_backup_version` to the new release and `restic_backup_binary_sha256` to the lines of
`restic_<version>_linux_amd64.bz2` and `restic_<version>_linux_arm64.bz2` in the release's
`SHA256SUMS` (check its signature, `SHA256SUMS.asc`, first), then run the role. Switching back to
`package` leaves `/usr/local/bin/restic` in place; delete it by hand.

## Testing

`molecule/default` converges the role on Debian 13 and Ubuntu 24.04 (systemd containers) with a
local repository and the distribution's package, runs it a second time and expects
`changed=0`, then `verify.yml` checks the controls in the table above. `prepare.yml` creates the
test data. `side_effect.yml` applies the role with a wrong password, which must stop without a
change, and then with the upstream release and the timers off; `verify_binary.yml` checks that
release against the repository that the package created.

```bash
cd roles/restic_backup && export MOLECULE_ROLE=restic_backup && molecule test
```

## Limitations

- Only a local repository is tested. S3-compatible buckets, SFTP, REST servers and the other
  backends, network failures during a backup and the time a backup and a restore take with real
  data and bandwidth are still to be checked against a real backend.
- The restore test proves that the files of the newest snapshot come back complete; it does not
  start an application on them or load a database dump. Restoring a database is a separate step
  (see the [mariadb role](../mariadb/README.md#dumps)).
- The status file and the metric show the last run without errors; a failed run only shows in the
  unit's state and the journal (and through the metric's age).
- One repository per host; the role sets up one backup job with one list of paths.
- When `restic_backup_textfile_dir` changes or is emptied, the old `restic_backup.prom` stays;
  delete it by hand.
- The restore test needs as much free space in `restic_backup_restore_test_dir` as it restores;
  a restored copy left by an interrupted test stays in `/var/tmp` (mode 0700) until it is
  deleted.
- Only x86_64 is tested.
