# Runbook

The collection runs nothing by itself. This page covers the services and timers that its roles
install on a host, and the failures of its CI and release automation.

## SSH login refused after the base role ran

| | |
|---|---|
| **Meaning** | `ssh` to a host that `luminare.infra_edge.base` configured ends with `Permission denied (publickey)` or a timeout. |
| **Impact** | Nobody can administer the host over SSH, and playbook runs against it fail as unreachable. |
| **Diagnosis** | A timeout points to the firewall (`base_mgmt_cidrs`, `base_ssh_allow_mode`) or a fail2ban ban; `Permission denied` points to the key, the user or the group: only members of `sshusers` with a listed key may log in, root never. From the host console: `nft list ruleset`, `fail2ban-client status sshd`, `journalctl -u ssh`, `sshd -T`. |
| **Mitigation** | Follow the [lock-out recovery](../roles/base/README.md#lock-out-recovery) steps on the console: stop nftables, unban the address, or add the key. |
| **Fix** | Correct the key lists, `base_mgmt_cidrs` or the group membership in the inventory and run the playbook again. |

## nftables did not load

| | |
|---|---|
| **Meaning** | `systemctl status nftables` shows `failed` after a change to `/etc/nftables.conf` or a file in `/etc/nftables.d/`. |
| **Impact** | The kernel keeps no ruleset from this file: with a failed start after a reboot the host has no firewall at all. |
| **Diagnosis** | `nft -c -f /etc/nftables.conf` names the file and line with the error; `journalctl -u nftables` shows the failed start. A drop-in must hold only `add rule inet filter input … accept` lines. |
| **Mitigation** | Move the broken drop-in out of `/etc/nftables.d/`, then `systemctl restart nftables` and `systemctl restart fail2ban`. |
| **Fix** | Correct the template of the role that wrote the drop-in; the roles check the ruleset with `nft -c` before they restart nftables. |

## Tunnel connector down or not connected

| | |
|---|---|
| **Meaning** | `systemctl status cloudflared` on a host with `luminare.infra_edge.cloudflared` shows `failed` or `activating (auto-restart)`, or `curl -s http://127.0.0.1:2000/ready` answers 503 (no connection to Cloudflare's edge). |
| **Impact** | The public hostnames of the tunnel answer with a Cloudflare error page (for example 1033) unless another connector of the same tunnel runs on a second host. |
| **Diagnosis** | `journalctl -u cloudflared -n 100` shows why: `Unauthorized` or a token parse error points to the token (rotated or wrong), `failed to dial` or timeouts point to outbound port 7844 (UDP and TCP) or DNS, `Failed to read token file` to `/etc/cloudflared/token` (mode 0600, owner `cloudflared`). The start waits up to 30 seconds for the first connection, then systemd restarts it every 5 seconds. |
| **Mitigation** | If QUIC (UDP 7844) is blocked on the way, add the two items `--protocol` and `http2` to `cloudflared_extra_args` and run the play; for a rotated token, export the new `TUNNEL_TOKEN` and run the play. |
| **Fix** | Correct the token, the outbound firewall or DNS, and run the playbook again; it rewrites the token file and restarts the connector. |

## A site answers 502 or nginx does not run

| | |
|---|---|
| **Meaning** | A public hostname of the tunnel that points to a site of `luminare.infra_edge.nginx` answers `502 Bad Gateway` (a page that says `nginx`), or `systemctl status nginx` shows `failed`. |
| **Impact** | The application behind that site is unreachable for visitors; with nginx down, every site is. |
| **Diagnosis** | `tail -n 20 /var/log/nginx/error.log` names the site and the upstream: `connect() failed (111: Connection refused)` means the application does not run or listens elsewhere, `upstream prematurely closed connection` that it failed during the request. `grep '"status":5' /var/log/nginx/access.log \| tail` lists the failed requests with `upstream_addr`. If nginx does not run, `nginx -t` names the file and line that it refuses (the unit runs the same check before it starts). |
| **Mitigation** | Start or restart the application. If nginx refuses its configuration, move the file that `nginx -t` names out of `/etc/nginx/sites-enabled/` or `/etc/nginx/conf.d/`, then `systemctl start nginx`. |
| **Fix** | Correct the `upstream` of the site or the application's listener, or the input that produced the broken file, and run the playbook again; it checks the whole configuration before it reloads nginx. |

## MariaDB does not run

| | |
|---|---|
| **Meaning** | `systemctl status mariadb` on a host with `luminare.infra_edge.mariadb` shows `failed` or `activating`, or the play stopped at "Check that mariadb runs after the restart". |
| **Impact** | Every application that uses a database on this host fails; the nightly dump fails too. |
| **Diagnosis** | `journalctl -u mariadb -n 50` names the reason: `Can't start server: Bind on TCP/IP port` points to `mariadb_bind_address` (an address the host does not have, or port 3306 taken), `unknown variable` or `COLLATION ... is not valid` to `/etc/mysql/mariadb.conf.d/60-tuning.cnf`, `Cannot allocate memory` or `mmap` errors to `mariadb_innodb_buffer_pool_size`, `No space left on device` to the disk (`df -h /var/lib/mysql`). |
| **Mitigation** | Move `/etc/mysql/mariadb.conf.d/60-tuning.cnf` out of the folder and `systemctl start mariadb`: the server starts with the package's settings (on `127.0.0.1`). |
| **Fix** | Correct the variable in the inventory and run the playbook again; it writes the file back and restarts the server. |

## Nightly MariaDB dump failed

| | |
|---|---|
| **Meaning** | `systemctl status mariadb-dump.service` shows `failed`, or `/var/backups/mariadb` has no file from the last night. |
| **Impact** | No new dump: the dumps from earlier nights stay (a failed run deletes nothing), so a backup tool copies only older data. |
| **Diagnosis** | `journalctl -u mariadb-dump.service -n 50` shows the error of `mariadb-dump`, `mariadb` or `zstd`: `Can't connect to local server through socket` means the server did not run at that time, `Access denied for user 'root'@'localhost'` that root lost its `unix_socket` login, `No space left on device` the disk of the dump folder. `systemctl list-timers mariadb-dump.timer` shows the last and next run. |
| **Mitigation** | Fix the cause and run `systemctl start mariadb-dump.service` once; it writes a complete set and then applies the retention. |
| **Fix** | For a full disk, lower `mariadb_dump_retention_days` or move `mariadb_dump_dir` to a larger disk; for root's login see [Troubleshooting](troubleshooting.md). |

## Backup recovery objectives

With the defaults of `luminare.infra_edge.restic_backup`, the recovery point objective is about
24 hours: one snapshot a night at 03:45 (host time), after the database dumps of 03:15, and a run
missed while the host was off follows at the next boot. The restore test and an alert on
`restic_backup_last_success_timestamp_seconds` treat a newest snapshot older than 26 hours
(`restic_backup_max_age_hours`) as a failure. The recovery time objective is not measured against
a real backend yet: in the Molecule containers, `restic-restore-test` restored the newest snapshot
(139 and 168 files, about 0.5 MB, from a local repository) in 0.8 seconds. With a real backend it
depends on the amount of data and the bandwidth, so run `restic-restore-test` on the host after
the first nights and note the time it prints.

## Nightly backup failed

| | |
|---|---|
| **Meaning** | `systemctl status restic-backup.service` on a host with `luminare.infra_edge.restic_backup` shows `failed`, or the metric `restic_backup_last_success_timestamp_seconds` (or `/var/lib/restic-backup/last-success`) is older than 26 hours. |
| **Impact** | No new snapshot, or one whose retention did not run: the snapshots of earlier nights stay, so a restore loses at most the changes since the last success. A failed `forget --prune` lets the repository grow. |
| **Diagnosis** | `journalctl -u restic-backup.service -n 50` shows the failed step: `these paths do not exist` names a path of `restic_backup_paths` that is gone; `Fatal: unable to open repository`, `connection refused` or timeouts point to the backend or the network; `wrong password or no key found` to the password (or a changed repository); `repository is already locked` to another restic run (the job waits up to two hours) or a stale lock of a killed run; `Warning: at least one source file could not be read` (exit code 3) to a file that vanished or could not be read during the backup. `systemctl list-timers restic-backup.timer` shows the last and next run. |
| **Mitigation** | Fix the cause and run `systemctl start restic-backup.service` once; it backs up, applies the retention and writes the status. For a stale lock (no other restic process runs on any host of the repository): `restic-env unlock`. |
| **Fix** | Correct `restic_backup_paths`, the repository or its credentials in the inventory and run the playbook; the role tries the new settings before it writes them. |

## Restore test failed

| | |
|---|---|
| **Meaning** | `/usr/local/sbin/restic-restore-test` ended with `FAILED` and exit code 1. |
| **Impact** | The newest snapshot is too old, or it could not be restored completely: a restore from it would also fail or miss files. |
| **Diagnosis** | The line after `FAILED` names the reason: `the newest snapshot is ... hours old` means the nightly backup did not run or failed (see above); `restic restore failed` shows restic's error (repository, lock, disk space in `/var/tmp`); a list of differences names files that are missing or have another size, mode or owner in the restored copy. Run it with `--keep` to look at the copy. |
| **Mitigation** | Run `systemctl start restic-backup.service` and then the test again; for differences, run `systemctl start restic-check.service` and read its journal. |
| **Fix** | A repeated difference after a successful check points to a bug: open an issue with the output of the test (it names paths and sizes, no file content). |

## Repository check failed

| | |
|---|---|
| **Meaning** | `systemctl status restic-check.service` shows `failed` after the monthly run or a start by hand. |
| **Impact** | The repository may hold damaged or missing data, so some snapshots may not restore. |
| **Diagnosis** | `journalctl -u restic-check.service -n 50`: `repository is already locked` is a backup or prune that ran longer than two hours, `pack ... not found` or `ciphertext verification failed` point to damaged data in the backend. |
| **Mitigation** | For a lock, start the check again later. For damaged data, keep the backend's data as it is and run `restic-env check --read-data` to see the extent. |
| **Fix** | Follow restic's [troubleshooting guide](https://restic.readthedocs.io/en/stable/077_troubleshooting.html) (`restic repair index`, `restic repair snapshots`), then run a backup and the restore test. |

## Security updates are not installed

| | |
|---|---|
| **Meaning** | Security updates stay pending (`apt list --upgradable` lists packages from the security archive for more than a day). |
| **Impact** | Known vulnerabilities stay open on the host. |
| **Diagnosis** | `systemctl list-timers 'apt-daily*'` shows the daily timers; `/var/log/unattended-upgrades/unattended-upgrades.log` shows the last run; `apt-config dump Unattended-Upgrade::Origins-Pattern APT::Periodic` shows the allowed origins and whether the daily run is on. A held package or a dpkg error stops the run. |
| **Mitigation** | Run `unattended-upgrade -d` once and read its output; install an urgent update by hand with `apt-get install --only-upgrade <package>`. |
| **Fix** | Remove the cause (held package, broken dpkg state) and check that `base_unattended_upgrades_enabled` is true. If `/var/run/reboot-required` exists, reboot in a maintenance window or set `base_unattended_reboot`. |

## Check failed: molecule

| | |
|---|---|
| **Meaning** | The aggregate `molecule` job failed: the `molecule-plan` job, at least one `molecule-scenario (<role>, <platform>)` job or at least one `molecule-edge (<platform>)` job did not pass. `<platform>` is `debian13` or `ubuntu2404`. |
| **Impact** | The pull request should not be merged; a role or the edge playbook may not converge, may not be idempotent or may fail its checks on Debian 13 or Ubuntu 24.04. |
| **Diagnosis** | Open the failed job. The summary at the end of the log names the Molecule action that failed (`converge`, `idempotence`, `verify`). A role job's instance is `ie-<role>-<platform>`; reproduce it locally in one shell: `cd roles/<role> && export MOLECULE_ROLE=<role>`, then `molecule test --platform-name ie-<role>-<platform> --destroy never`, then `molecule login --host ie-<role>-<platform>` (every Molecule command of a role needs `MOLECULE_ROLE` set, otherwise the instance names do not match). An edge job's instance is `ie-edge-<platform>`; from the repository root run `molecule test --scenario-name edge --platform-name ie-edge-<platform> --destroy never`, then `molecule login --scenario-name edge --host ie-edge-<platform>`. A failed probe in its verify step names the source host, the port, the result and the expected result; `nft list ruleset` and `ip netns exec lan ip address` in the instance show the firewall and the addresses of the hosts outside. |
| **Mitigation** | If the log shows a download or package mirror error, re-run the failed jobs once. |
| **Fix** | Fix the role, the playbook, the example inventory or the scenario in the same pull request. Afterwards remove the containers with `molecule destroy` (in a role's folder with `MOLECULE_ROLE` still set, or `molecule destroy --scenario-name edge` from the repository root). |

## Scheduled CI run failed without a code change

| | |
|---|---|
| **Meaning** | The weekly `ci` run (Tuesdays 03:41 UTC) failed although `main` did not change. |
| **Impact** | None for users yet; a role no longer converges or is no longer idempotent with the current Debian or Ubuntu packages, or a lint or tool update changed a result. |
| **Diagnosis** | Compare the failing job with the last passing run of the same job: look for package versions in the converge output and for a recently merged Dependabot pull request (base image digests, Python tools). |
| **Mitigation** | Open an issue with the failing job link, so that pull requests are not blamed for the failure. |
| **Fix** | Adapt the role to the new package version, or pin the package in the role with a comment and a follow-up issue. |

## Release build failed: galaxy.yml has a different version than the tag

| | |
|---|---|
| **Meaning** | The `build` job of the release stopped with `galaxy.yml has version …, the tag is v…`: the release pull request did not update `galaxy.yml`. |
| **Impact** | The GitHub release stays a draft without files, so nothing reaches users. |
| **Diagnosis** | `git show vX.Y.Z:galaxy.yml \| grep '^version'` shows the old version. Check that the `version:` line still ends with `# x-release-please-version` and that `release-please-config.json` lists `galaxy.yml` under `extra-files`. |
| **Mitigation** | None needed; the previous release stays the latest one. |
| **Fix** | Restore the annotation or the `extra-files` entry in a pull request with a `fix:` title, delete the empty draft release, and let release-please prepare the next version. |

## The release pull request shows no checks

| | |
|---|---|
| **Meaning** | release-please opens its pull request with the workflow token, and such pull requests do not start workflows. |
| **Impact** | The required checks never report, so the pull request cannot be merged. |
| **Diagnosis** | The pull request `chore(main): release X.Y.Z` has no `ci / lint-test` check. |
| **Mitigation** | Close the pull request and reopen it once; the checks then run. |
| **Fix** | None; this is how GitHub treats the workflow token (see [ADR 0004](adr/0004-draft-releases-with-checksums-and-provenance.md)). |
