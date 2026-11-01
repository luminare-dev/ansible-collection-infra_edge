# luminare.infra_edge.restic_backup

Encrypted nightly backups with [restic](https://restic.net/) for a Debian 13 or Ubuntu 24.04
host: a sandboxed service backs up `/etc` and `/var/backups` (with the dumps of the
[`mariadb`](../mariadb/README.md) role) to a repository off the host and thins out old snapshots
with `forget --prune`. A monthly `restic check`, a status file (optionally a node_exporter
metric) and a restore test come with it. restic comes from the distribution, or optionally as a
pinned upstream release checked against its SHA-256.

## Requirements

- Debian 13 or Ubuntu 24.04 (x86_64 or aarch64), reached as root or with `become: true`.
- A restic repository per host (S3-compatible, SFTP, REST or another backend). The role creates
  it if it does not exist yet.
- The password and backend credentials from Ansible Vault or SOPS. Keep a copy of the password
  outside the host and the repository: without it the snapshots cannot be read.

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

The playbook [`luminare.infra_edge.edge`](../../playbooks/edge.yml) runs the role when
`edge_restic_backup_enabled` is true.

## What it sets up

- Settings, password and excludes in `/etc/restic` (root only). Every restic run goes through
  `/usr/local/sbin/restic-env`, so no secret is on a command line or in a unit.
- New settings are tried against the repository first; a wrong password or a backend error stops
  the role before the old, working settings are replaced.
- `restic-backup.timer` at 03:45 (after the dumps at 03:15) and `restic-check.timer` monthly,
  both with sandboxed services. A missing backup path fails the run.
- `/var/lib/restic-backup/last-success` and, with `restic_backup_textfile_dir`, the metric
  `restic_backup_last_success_timestamp_seconds`.

## Variables

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

`restic_backup`, `restic_backup_install`, `restic_backup_repository`, `restic_backup_jobs`. The
input checks always run.

## Using it on the host

```bash
systemctl start restic-backup.service          # back up now
journalctl -u restic-backup.service -n 20
restic-env snapshots
restic-env restore latest --target /var/tmp/restore --include /var/backups/mariadb
```

A database comes back from its dump as described in the
[mariadb role](../mariadb/README.md#dumps).

## Restore test

`restic-restore-test` (as root) restores the newest snapshot of the host into a folder in
`/var/tmp`, compares it with the snapshot listing and prints `passed` or `FAILED` with the reason
(exit code 1). It also fails when the snapshot is older than `restic_backup_max_age_hours` (26).
`--keep` keeps the restored copy. It needs as much free space as it restores.

An alert on the metric:

```promql
time() - restic_backup_last_success_timestamp_seconds > 26 * 3600
```

## Repository backends

The role writes `restic_backup_repository` and `restic_backup_env` as given; see restic's
[documentation](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html):

```yaml
# S3-compatible bucket
restic_backup_repository: s3:https://s3.example.com/edge-backups/edge-01
restic_backup_env:
  AWS_ACCESS_KEY_ID: "{{ vault_backup_s3_key_id }}"
  AWS_SECRET_ACCESS_KEY: "{{ vault_backup_s3_secret }}"

# SFTP: the key and the server's host key must be in /root/.ssh first
restic_backup_repository: sftp:backup@example.com:/srv/restic/edge-01

# REST server
restic_backup_repository: "rest:https://edge-01:{{ vault_backup_rest_password }}@backup.example.com/edge-01/"
```

Give every host its own repository: check and prune lock the whole repository.

## Upgrading restic (binary method)

Set `restic_backup_version` and `restic_backup_binary_sha256` (from the release's signed
`SHA256SUMS`), then run the role. Switching back to `package` leaves `/usr/local/bin/restic` in
place; delete it by hand.

## Testing

```bash
cd roles/restic_backup && export MOLECULE_ROLE=restic_backup && molecule test
```

## Limitations

- Only a local repository is tested; real backends are not.
- The restore test checks the files, not that a database dump loads or an application starts.
- One backup job with one list of paths per host.
