# luminare.infra_edge.base

Base hardening for a Debian 13 or Ubuntu 24.04 edge host: time zone, locales and host name,
unattended security upgrades, an admin and an automation user that log in with SSH keys only,
an SSH server hardened by
[`devsec.hardening.ssh_hardening`](https://github.com/dev-sec/ansible-collection-hardening/tree/master/roles/ssh_hardening),
a default-drop nftables firewall with a drop-in folder for the other roles, fail2ban for SSH
and journal limits.

## Requirements

- Debian 13 or Ubuntu 24.04 with Python 3, reached as root or with `become: true`.
- ansible-core 2.20+ with `devsec.hardening` 11.x, `community.general` 13.x and `ansible.posix`
  2.x (installed as dependencies of the collection).
- At least one SSH key for each user, and the management networks that may reach SSH (or
  `base_ssh_allow_mode: any`). The role checks both before it changes anything.

## Example playbook

```yaml
- name: Harden the edge hosts
  hosts: edge
  become: true
  roles:
    - role: luminare.infra_edge.base
      vars:
        base_admin_ssh_keys:
          - "ssh-ed25519 AAAA... admin@laptop"
        base_automation_ssh_keys:
          - "ssh-ed25519 AAAA... ansible@controller"
        base_admin_password_hash: "{{ vault_base_admin_password_hash }}"  # openssl passwd -6
        base_mgmt_cidrs:
          - 192.0.2.0/24
          - 2001:db8::/32
```

Run the first play as root (or the cloud image's user) and switch `ansible_user` to the
automation user afterwards: root can no longer log in over SSH, and other users only if they
are in the `sshusers` group.

## What it sets up

- SSH: keys only, no root login, `AllowGroups sshusers`, `MaxAuthTries 3`, devsec's algorithm
  and forwarding defaults; on Ubuntu `ssh.socket` is masked.
- Admin user with sudo and its password; automation user with passwordless sudo
  (`/etc/sudoers.d/90-base-automation`). `authorized_keys` holds exactly the configured keys.
- `unattended-upgrades` for the security archive, no automatic reboot by default.
- `/etc/nftables.conf` with input and forward policy drop, SSH only per `base_ssh_allow_mode`;
  `ufw` is removed.
- fail2ban `sshd` jail (management networks are never banned), journal limited to 500 MB and
  14 days.
- Optional: `devsec.hardening.os_hardening` with `base_os_hardening_enabled` (not tested).

## Variables

<!-- argument-specs:base:begin -->
| Variable | Type | Default | Description |
|---|---|---|---|
| `base_timezone` | str | `Europe/Vienna` | Time zone of the host, a name from the tz database. |
| `base_locales` | list of str | `["en_US.UTF-8"]` | Locales to generate. |
| `base_default_locale` | str | `en_US.UTF-8` | System-wide LANG in /etc/default/locale; must be one of base_locales. |
| `base_hostname` | str | `{{ inventory_hostname }}` | Host name to set, and to map to 127.0.1.1 in /etc/hosts. An empty string leaves both unchanged. Must be a valid host name (RFC 1123: letters, digits and hyphens in dot-separated labels, at most 64 characters) and not an IP address; the role stops before any change otherwise. Set it, or set it to "", when the inventory names hosts by IP address or with underscores. |
| `base_manage_hosts_file` | bool | `true` | Keep a 127.0.1.1 line for base_hostname in /etc/hosts. |
| `base_timesyncd_enabled` | bool | `true` | Install systemd-timesyncd for time synchronisation. Set false on hosts that use chrony or ntpsec, which the package would replace. |
| `base_qemu_guest_agent` | bool | `false` | Install qemu-guest-agent (for virtual machines on a QEMU/KVM hypervisor). |
| `base_unattended_upgrades_enabled` | bool | `true` | Install security updates every day with unattended-upgrades. False keeps the package but turns the daily run off. |
| `base_unattended_upgrades_origins` | list of str | `[]` | Origins-Pattern entries that unattended-upgrades may install from. Empty means the security archive of the distribution only. |
| `base_unattended_reboot` | bool | `false` | Reboot automatically when an update requires it. |
| `base_unattended_reboot_time` | str | `04:30` | Time of day (HH:MM) for the automatic reboot when base_unattended_reboot is true. |
| `base_admin_user` | str | `admin` | Name of the personal admin account. It may use sudo with its password. |
| `base_admin_ssh_keys` | list of str | `[]` | Public SSH keys of the admin user. Required (at least one), because password logins are off; the list replaces all other keys of the user. |
| `base_admin_password_hash` | str | `""` | SHA-512 crypt hash (openssl passwd -6) of the admin password, needed for sudo and the console. Empty leaves the password unchanged; a new user then has a locked password. Keep the value in a vault. |
| `base_automation_user` | str | `ansible` | Name of the account that Ansible and other automation log in with. |
| `base_automation_ssh_keys` | list of str | `[]` | Public SSH keys of the automation user. Required (at least one); the list replaces all other keys of the user. |
| `base_automation_sudo_nopasswd` | bool | `true` | Let the automation user use sudo without a password. False makes sudo ask for the user's password, which this role does not set (a new account keeps a locked password), so sudo stays unusable for it until a password is set by other means. |
| `base_ssh_group` | str | `sshusers` | Group whose members may log in over SSH (AllowGroups). The admin and the automation user are added to it; other roles add their own users. |
| `base_ssh_hardening_enabled` | bool | `true` | Harden the SSH server with devsec.hardening.ssh_hardening (key-only login, no root login, AllowGroups, MaxAuthTries). |
| `base_ssh_port` | int | `22` | Port of the SSH server, used by the SSH server, the firewall rule and the fail2ban jail. |
| `base_ssh_listen_addresses` | list of str | `["0.0.0.0", "::"]` | Addresses the SSH server listens on (ListenAddress). The default covers IPv4 and IPv6; an address family the host does not have is skipped by the SSH server. |
| `base_sshd_max_auth_tries` | int | `3` | MaxAuthTries of the SSH server. |
| `base_os_hardening_enabled` | bool | `false` | Also apply devsec.hardening.os_hardening (sysctl, PAM, login.defs, file permissions). Opt-in; read the role README first, it turns IP forwarding off. |
| `base_firewall_enabled` | bool | `true` | Write and load the nftables firewall (input and forward policy drop) with the drop-in directory /etc/nftables.d. Removes ufw. |
| `base_ssh_allow_mode` | str: `mgmt_cidrs`, `loopback`, `any` | `mgmt_cidrs` | Where the firewall accepts SSH from. mgmt_cidrs means only from base_mgmt_cidrs, loopback means no SSH rule (only local or tunnelled access), any means from everywhere. |
| `base_mgmt_cidrs` | list of str | `[]` | IPv4 and IPv6 networks (CIDR) of the management hosts. Required when base_ssh_allow_mode is mgmt_cidrs; fail2ban never bans them. |
| `base_fail2ban_enabled` | bool | `true` | Install fail2ban with an SSH jail (systemd journal backend, nftables ban action). Also installs nftables for the ban action when base_firewall_enabled is false; fail2ban then adds its own nftables table and leaves the other rules of the host alone. |
| `base_fail2ban_maxretry` | int | `5` | Failed SSH logins within base_fail2ban_findtime that cause a ban. |
| `base_fail2ban_findtime` | str | `10m` | Time window for counting failed SSH logins (fail2ban time format). |
| `base_fail2ban_bantime` | str | `1h` | How long an address stays banned (fail2ban time format). |
| `base_journald_persistent` | bool | `true` | Keep the journal on disk (Storage=persistent) instead of in memory. |
| `base_journald_system_max_use` | str | `500M` | Disk space limit of the journal (SystemMaxUse). |
| `base_journald_max_retention` | str | `14day` | Maximum age of journal entries (MaxRetentionSec). |
<!-- argument-specs:base:end -->

The SSH settings above are passed to `devsec.hardening.ssh_hardening` as role parameters, so an
inventory variable cannot weaken them. Other variables of that role still work, for example
`ssh_allow_tcp_forwarding: local`.

## Firewall drop-ins for other roles

`base` owns `/etc/nftables.conf`, which ends with `include "/etc/nftables.d/*.nft"`. Another role
opens a port by writing `/etc/nftables.d/<NN>-<role>.nft` with `add rule inet filter input …
accept` lines only:

```text
add rule inet filter input ip saddr { 198.51.100.0/24 } tcp dport 3306 accept comment "mariadb"
```

Numbers in use: 20 web server, 30 database, 40 to 49 application ports, 50 metrics exporters.
The role checks the whole ruleset with `nft -c -f /etc/nftables.conf` before it restarts
nftables, and restarts fail2ban with it.

## Tags

`base` and one per part: `packages`, `system`, `unattended_upgrades`, `users`, `ssh`,
`firewall`, `fail2ban`, `journald`, `os_hardening`. The input checks always run.

## Lock-out recovery

If a wrong key list or management network locks you out:

1. Log in on the host console (hypervisor or provider web console, or the rescue system) as the
   admin user with its password.
2. Firewall: `nft list ruleset`; `systemctl stop nftables` opens the host until the next run.
3. fail2ban: `fail2ban-client status sshd`, then `fail2ban-client unban <address>`.
4. SSH: `sshd -T | grep -E 'allowgroups|permitrootlogin|authenticationmethods'` and
   `journalctl -u ssh`; add the key or `usermod -aG sshusers <user>`.
5. Fix the inventory and run the playbook again.

## Testing

```bash
cd roles/base && export MOLECULE_ROLE=base && molecule test
```

## Limitations

- Molecule does not load the nftables ruleset or start fail2ban in the role scenario (the `edge`
  scenario does); behaviour after a reboot and on real interfaces is not tested.
- `flush ruleset` and the forward drop policy remove Docker's rules: use
  `base_firewall_enabled: false` on hosts that run Docker or route traffic.
- devsec writes the whole `/etc/ssh/sshd_config` without including `sshd_config.d/`, so drop-ins
  there (for example from cloud-init) are ignored; use `sshd_custom_options`. A smaller RSA host
  key is replaced by a 4096-bit one on the first run.
