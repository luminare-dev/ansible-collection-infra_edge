# Upgrading

Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html), with the rules for
versions before 1.0.0 below. Each release is a git tag `vX.Y.Z` with a GitHub release; the
[changelog](../CHANGELOG.md) lists every change, breaking ones under "BREAKING CHANGES".

## Version policy

| Release | Before 1.0.0 (now) | From 1.0.0 |
|---|---|---|
| Patch (`0.1.0` to `0.1.1`) | Fixes only, never a breaking change | Fixes only |
| Minor (`0.1.x` to `0.2.0`) | New roles, variables or features, and it may contain breaking changes | New roles, variables or features, never a breaking change |
| Major (`1.x` to `2.0.0`) | | Breaking changes |

A change is breaking when an unchanged inventory would fail or would set up a host differently
after the upgrade, for example:

- a variable, a role or the playbook is renamed or removed, or a variable gets another type;
- a default changes what a host gets: a port, an address, a path, a user, a package or a
  schedule;
- a distribution is dropped, or `requires_ansible` rises to a newer ansible-core;
- a file that the roles share or leave behind moves, for example the drop-in numbers in
  `/etc/nftables.d` or the dump folder.

A breaking change is named in the changelog with the steps to adapt the inventory, and gets a
section under [Version notes](#version-notes). Fixes go into the latest minor release only, so
upgrade within 0.x when a new minor release comes out, and pin the tag in `requirements.yml` so
that a new release never arrives unplanned.

## General steps

1. Read the changelog entries between your version and the new one.
2. Back up what the roles change on your hosts (configuration, data).
3. Install the new release (see [Installation](install.md)) and verify its checksum. With a
   `requirements.yml`, change the `version:` tag and run
   `ansible-galaxy collection install -r requirements.yml --force`.
4. Run your playbook with `--limit` against one host first, then against all of them, and run the
   check from [Installation](install.md) again.

## Version notes

### 0.2.0

Adds the role `restic_backup` and the switch `edge_restic_backup_enabled` of the playbook
`luminare.infra_edge.edge`, which is off by default: an inventory of 0.1.0 sets up the same host.

- The example inventory in `examples/edge/` now switches the backups on. A copy of the new example
  needs `restic_backup_repository` per host in `inventory.yml` and the three backup values in the
  vault file (see the [example's README](../examples/edge/README.md)), or
  `edge_restic_backup_enabled: false`.
- Switching the backups off later does not remove them from a host: run the playbook once with
  `restic_backup_timers_enabled: false` (and the switch still on) to stop the timers.

### 0.1.0

The first release; there is nothing to migrate from. On a host that was set up before, by hand or
with other roles, the first run replaces some of that setup:

- `base` removes ufw and writes `/etc/nftables.conf`, whose `flush ruleset` also removes rules
  that other software added (keep `base_firewall_enabled: false` on hosts that run Docker). SSH
  then accepts only keys of users in the `sshusers` group, and never root; list every key that
  still needs access in `base_admin_ssh_keys` or `base_automation_ssh_keys` first.
- `cloudflared` replaces a connector set up with `cloudflared service install`, removes its
  self-update units and installs the pinned version, also when a newer one was installed.
- `nginx` replaces `/etc/nginx/nginx.conf` and removes the package's default site; files in
  `/etc/nginx/conf.d/` stay and are checked with the rest by `nginx -t`.
- `mariadb` logs in as root over the socket without a password, so a root password set by hand
  stops the role (see [Troubleshooting](troubleshooting.md)). It removes anonymous accounts, the
  `test` database and root accounts for other hosts, and never drops another database or account.
