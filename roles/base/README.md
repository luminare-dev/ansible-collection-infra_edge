# luminare.infra_edge.base

Base hardening for a Debian 13 or Ubuntu 24.04 edge host: time zone, locales and host name,
unattended security upgrades, an admin user and an automation user that log in with SSH keys
only, an SSH server hardened by
[`devsec.hardening.ssh_hardening`](https://github.com/dev-sec/ansible-collection-hardening/tree/master/roles/ssh_hardening),
a default-drop nftables firewall with a drop-in directory for the other roles of this collection,
fail2ban for SSH and a size and age limit for the systemd journal.

## Requirements

- Managed host: Debian 13 or Ubuntu 24.04 with Python 3, reached as root or with `become: true`.
  The role stops before any change on another distribution.
- Control node: ansible-core 2.20 or later and the collections `devsec.hardening` (11.x),
  `community.general` (13.x) and `ansible.posix` (2.x). `ansible-galaxy collection install`
  pulls them in as dependencies of `luminare.infra_edge`.
- At least one public SSH key for each of the two users, and the management networks that may
  reach SSH (or `base_ssh_allow_mode: any`). The role checks both before it changes anything.

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

On a new host, run the first play as root (or as the user of the cloud image) and switch
`ansible_user` to the automation user afterwards: root can no longer log in over SSH once the
role has run, and other users can log in only if they are in the `sshusers` group.

## Controls

| Control | How | Checked in Molecule |
|---|---|---|
| SSH: keys only | `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `AuthenticationMethods publickey` | `sshd -T`; a password login is refused |
| SSH: no root login | `PermitRootLogin no` | `sshd -T`; root with a valid key is refused although the test puts root into `sshusers` |
| SSH: only the SSH group | `AllowGroups sshusers`; the admin and the automation user are members | a user outside the group with a valid key is refused |
| SSH: few attempts per connection | `MaxAuthTries 3` | `sshd -T` |
| SSH: current algorithms, no forwarding | devsec defaults: ciphers, MACs and key exchange chosen for the installed OpenSSH, 4096-bit RSA host key, short Diffie-Hellman moduli removed from `/etc/ssh/moduli`, TCP/agent/X11 forwarding and tunnels off | config written and accepted by `sshd -t` |
| SSH: one configuration file | `/etc/ssh/sshd_config` is written by devsec and validated with `sshd -T` before it is replaced; on Ubuntu the `ssh.socket` activation is masked so that the port and listen addresses apply | `ssh.socket` masked, `ssh.service` running |
| Separate admin and automation users | admin: sudo with its password (group `sudo`); automation user: sudo without a password (`/etc/sudoers.d/90-base-automation`, checked with `visudo`) | `sudo -l -U`, `visudo -c` |
| Authorized keys are exactly the configured ones | `authorized_key` with `exclusive: true` | key login works, file content compared |
| Security updates | `unattended-upgrades` with only the security archive allowed, daily run on, reboot off by default | `apt-config dump` |
| Firewall: input and forward drop | `/etc/nftables.conf` with policy drop, loopback, established/related, ICMP and DHCPv6 replies (UDP 546 from `fe80::/10`) accepted, SSH only per `base_ssh_allow_mode`; `ufw` removed | file content; `nft -c -f` passes without and with a valid drop-in and fails with a broken one; the `ufw` that the test installs is gone |
| Brute-force bans | fail2ban `sshd` jail, systemd journal backend, nftables ban action (nftables is installed for it also when `base_firewall_enabled` is false), management networks never banned | jail file; `fail2ban-client -t` |
| Journal limits | `Storage=persistent`, `SystemMaxUse=500M`, `MaxRetentionSec=14day` | `systemd-analyze cat-config`, `/var/log/journal` exists |
| Time and locale | time zone (default `Europe/Vienna`), locales, `LANG`, systemd-timesyncd | `timedatectl`, `locale -a` |
| Host name | host name and a `127.0.1.1` line in `/etc/hosts`; the role stops before any change when `base_hostname` (default: the inventory name) is an IP address or not a valid RFC 1123 host name | `/etc/hosts`; the input checks accept 2 valid names and refuse 6 invalid ones (IPv4, IPv6, underscore, leading or trailing hyphen, 65 characters) |
| Operating system hardening (opt-in) | `devsec.hardening.os_hardening` when `base_os_hardening_enabled` is true | not tested |

Loading the firewall into the kernel and starting fail2ban are tagged `molecule-notest` and are
not run in Molecule (see [Limitations](#limitations)).

## Variables

The table is generated from [`meta/argument_specs.yml`](meta/argument_specs.yml), which Ansible
also uses to check the variables when the role starts.

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
inventory variable cannot weaken them. Every other variable of that role can still be set in the
inventory, for example `ssh_allow_tcp_forwarding: local` to allow `ssh -L` for an admin who
reaches a loopback-only web interface, or `ssh_client_alive_interval`.

## Firewall drop-ins for other roles

`base` owns `/etc/nftables.conf`. Its last line is `include "/etc/nftables.d/*.nft"`, and the
input policy is drop, so another role opens a port by writing `/etc/nftables.d/<NN>-<role>.nft`
with `add rule inet filter input … accept` lines only:

```text
add rule inet filter input ip saddr { 198.51.100.0/24 } tcp dport 3306 accept comment "mariadb"
```

Numbers in use: 20 web server, 30 database, 40 to 49 application ports, 50 metrics exporters. Such a role
writes its file only if `/etc/nftables.d` exists (or when told to), checks the whole ruleset
with `nft -c -f /etc/nftables.conf` and restarts `nftables`. Restarting nftables flushes the
ruleset, so fail2ban is restarted with it. [ADR 0009](../../docs/adr/0009-nftables-ruleset-with-drop-in-directory.md)
explains the convention.

## Tags

`base` (every task) and one tag per part: `packages`, `system`, `unattended_upgrades`, `users`,
`ssh`, `firewall`, `fail2ban`, `journald`, `os_hardening`. The checks at the start always run.
Skipping `firewall` or `fail2ban` also skips the handlers that restart those services.

## Lock-out recovery

The role checks its inputs first, keeps established connections open when the firewall loads,
and validates the SSH and firewall files before it replaces them, but a wrong key list or
management network can still lock everyone out on the next login. Recovery:

1. Open the console of the host (hypervisor console, the web console of the hosting provider, or
   its rescue system) and log in as the admin user with its password, or as root with the root
   password if one is set.
2. Firewall: `nft list ruleset` shows the loaded rules; `systemctl stop nftables` (or
   `nft flush ruleset`) opens the host until the next run. Correct `base_mgmt_cidrs` or
   `base_ssh_allow_mode` in the inventory.
3. fail2ban: `fail2ban-client status sshd` lists the banned addresses;
   `fail2ban-client unban <address>` removes one.
4. SSH: `sshd -T | grep -E 'allowgroups|permitrootlogin|authenticationmethods'` shows what the
   server enforces; `journalctl -u ssh` shows why a login was refused. Add the missing key to
   `~/.ssh/authorized_keys` of the user, or add the user to `sshusers` (`usermod -aG sshusers <user>`).
5. Fix the inventory and run the playbook again; it replaces the manual changes.

## Testing

`molecule/default` converges the role on Debian 13 and Ubuntu 24.04 (systemd containers), runs
it a second time and expects `changed=0`, then checks the controls in the table above, including
real SSH logins to `127.0.0.1` inside the container: the automation user and admin get in with
the test key, root and a user outside `sshusers` are refused with the same key, and a password
login is refused. It also runs the role's input checks with valid and invalid host names
(`molecule/default/tasks/hostname_check.yml`). `prepare.yml` generates the key pair in the
container (the repository holds no key material), puts root into `sshusers`, so that only
`PermitRootLogin no` can refuse it, and installs `ufw`, so that the converge has to remove it.

```bash
cd roles/base && export MOLECULE_ROLE=base && molecule test
```

## Limitations

- Containers share the kernel of the test machine, so Molecule does not load the nftables
  ruleset or start fail2ban (tag `molecule-notest`). That `nft list ruleset` shows the drop
  policies on a booted host, that a port without a drop-in is closed from outside, that a host
  with DHCPv6 keeps its IPv6 address after a lease renewal, and that fail2ban bans an address
  after failed logins are still to be checked on a virtual machine.
- `base_os_hardening_enabled` is not tested: `os_hardening` sets kernel parameters, which in a
  privileged container would change the kernel of the test machine. It also turns IP forwarding
  off, which breaks hosts that run Docker or route traffic, unless its `sysctl_overwrite`
  variable allows forwarding.
- `flush ruleset` and the forward policy drop remove the rules that Docker creates. Hosts that
  run Docker need `base_firewall_enabled: false` or their own firewall plan. fail2ban then still
  bans with its own nftables table (the role installs nftables for it); Molecule does not test
  this combination.
- devsec writes the whole `/etc/ssh/sshd_config` without an `Include` of
  `/etc/ssh/sshd_config.d/`, so drop-ins there (for example from cloud-init) are not read;
  extra options go into devsec's `sshd_custom_options` variable. On its first run devsec replaces
  a smaller RSA host key with a 4096-bit one, which changes that host key's fingerprint.
- `base_qemu_guest_agent` only installs the package; the agent starts when the hypervisor offers
  its device.
