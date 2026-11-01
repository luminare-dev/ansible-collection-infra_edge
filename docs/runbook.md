# Runbook

What to check when one of the services or timers the roles install fails. Error messages of the
roles themselves are in [Troubleshooting](troubleshooting.md).

## SSH login refused after the base role ran

- A timeout points to the firewall (`base_mgmt_cidrs`, `base_ssh_allow_mode`) or a fail2ban ban;
  `Permission denied` to the key or the group (only members of `sshusers`, never root).
- On the console: `nft list ruleset`, `fail2ban-client status sshd`, `journalctl -u ssh`, `sshd -T`.
- Follow the [lock-out recovery](../roles/base/README.md#lock-out-recovery), fix the inventory and
  run the playbook again.

## nftables did not load

- `nft -c -f /etc/nftables.conf` names the file and line; a drop-in may only hold
  `add rule inet filter input … accept` lines.
- Move the broken drop-in out of `/etc/nftables.d/`, then restart `nftables` and `fail2ban`.

## Tunnel connector down

- `journalctl -u cloudflared -n 100`: `Unauthorized` means a wrong or rotated token, `failed to
  dial` means outbound port 7844 (UDP and TCP) or DNS is blocked.
- `curl -s http://127.0.0.1:2000/ready` answers 503 while there is no connection.
- If UDP 7844 is blocked, add `--protocol` and `http2` to `cloudflared_extra_args`. For a new token,
  export `TUNNEL_TOKEN` and run the playbook.

## A site answers 502 or nginx does not run

- `tail -n 20 /var/log/nginx/error.log`: `Connection refused` means the application is down or
  listens elsewhere.
- If nginx does not start, `nginx -t` names the file it refuses; move it out of
  `/etc/nginx/sites-enabled/` or `/etc/nginx/conf.d/` and start nginx.

## MariaDB does not run

- `journalctl -u mariadb -n 50`: a bind error points to `mariadb_bind_address`, `unknown variable`
  to `60-tuning.cnf`, memory errors to `mariadb_innodb_buffer_pool_size`.
- Moving `/etc/mysql/mariadb.conf.d/60-tuning.cnf` away starts the server with the package
  defaults. Fix the inventory and run the playbook again.

## Nightly MariaDB dump failed

- `journalctl -u mariadb-dump.service -n 50`; a failed run deletes no older dumps.
- Fix the cause and run `systemctl start mariadb-dump.service` once.

## Backups

With the defaults there is one snapshot a night at 03:45 (after the dumps at 03:15), so up to 24
hours of changes can be lost. Run `restic-restore-test` after the first nights to see how long a
restore takes with your data.

- **Backup failed:** `journalctl -u restic-backup.service -n 50` names the step (missing path,
  backend, password, lock). Fix it and run `systemctl start restic-backup.service`. For a stale
  lock with no other restic running: `restic-env unlock`.
- **Restore test failed:** the line after `FAILED` gives the reason (snapshot too old, restore
  error, or a list of differences). Run with `--keep` to inspect the copy.
- **Check failed:** `journalctl -u restic-check.service -n 50`. For damaged data follow restic's
  [troubleshooting guide](https://restic.readthedocs.io/en/stable/077_troubleshooting.html).

## Security updates are not installed

- `systemctl list-timers 'apt-daily*'` and `/var/log/unattended-upgrades/unattended-upgrades.log`.
- Run `unattended-upgrade -d` once to see why. Reboot if `/var/run/reboot-required` exists.

## CI and releases

- **molecule failed:** reproduce locally with
  `cd roles/<role> && export MOLECULE_ROLE=<role> && molecule test --destroy never`, or
  `molecule test --scenario-name edge` from the repository root. Re-run once for mirror errors.
- **Release build says galaxy.yml has a different version:** the `version:` line in `galaxy.yml`
  lost its `# x-release-please-version` comment.
- **Release PR shows no checks:** close and reopen it; PRs opened with the workflow token do not
  start workflows.
