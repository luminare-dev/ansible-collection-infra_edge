# Configuration

Each role of the collection is configured through its own variables. Every variable starts with
the role name (for example `<role>_enabled`), has its default in `roles/<role>/defaults/main.yml`
and is described, with its type, in `roles/<role>/meta/argument_specs.yml`, which Ansible checks
when the role starts. Each role gets a section on this page with a table of its options (variable,
type, default, description), generated from that file with `python3 tests/role_docs.py --write`;
a unit test fails when a table here or in a role README is out of date.

## base

[`luminare.infra_edge.base`](../roles/base/README.md) hardens the host: time zone and locales,
unattended security upgrades, the admin and automation users with SSH keys, the SSH server
(through `devsec.hardening.ssh_hardening`), the nftables firewall, fail2ban and the journal
limits. `base_admin_ssh_keys`, `base_automation_ssh_keys` and, with the default
`base_ssh_allow_mode`, `base_mgmt_cidrs` must be set; the role stops before any change
otherwise. Every other devsec `ssh_*` variable can be set in the inventory as well.

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

## cloudflared

[`luminare.infra_edge.cloudflared`](../roles/cloudflared/README.md) runs the connector of a
remotely managed tunnel: a pinned cloudflared version (package file checked against its SHA-256,
held with an apt pin), the tunnel token in a file that only the service user can read, and a
sandboxed systemd service with its metrics listener on `127.0.0.1:2000`. `cloudflared_token` must
be set; by default it is read from the environment variable `TUNNEL_TOKEN` of the control node.
`cloudflared_version` and `cloudflared_deb_sha256` change together.

<!-- argument-specs:cloudflared:begin -->
| Variable | Type | Default | Description |
|---|---|---|---|
| `cloudflared_version` | str | `2026.10.2` | cloudflared version to install and hold with an apt pin. Change it together with cloudflared_deb_sha256. |
| `cloudflared_deb_sha256` | dict | `{"amd64": "30a9a127c24ea8365fa8e11b13684128f34dd8a1137599aa00b4bebda1a0a083", "arm64": "2e5335ea0ef2fa98e5354357e77aaf453f3756d1f9023cf5b063409e1fb3baca"}` | SHA-256 of the package file of cloudflared_version per Debian architecture (the checksums of cloudflared-linux-amd64.deb and cloudflared-linux-arm64.deb in the GitHub release). The role stops on a host whose architecture has no entry, and when the downloaded file does not match. |
| `cloudflared_repository_url` | str | `https://pkg.cloudflare.com/cloudflared` | Cloudflare's apt repository. The package file of the pinned version comes from its pool (pool/main/c/cloudflared/), and the apt source points to it. |
| `cloudflared_apt_repository_enabled` | bool | `true` | Add the signed apt repository (key in /usr/share/keyrings/cloudflare-main.gpg, source in /etc/apt/sources.list.d/cloudflared.list), so that apt policy cloudflared shows newer versions; the apt pin keeps the installed one. False leaves the apt sources unchanged. |
| `cloudflared_apt_key_url` | str | `https://pkg.cloudflare.com/cloudflare-main.gpg` | Signing key of the apt repository. It is downloaded on every run and replaced when it changed, so a new key from Cloudflare reaches the host with the next run. |
| `cloudflared_token` | str | `{{ lookup('ansible.builtin.env', 'TUNNEL_TOKEN') }}` | Token of the remotely managed tunnel (from the tunnel's install command in the Cloudflare dashboard or from the API). Required. The default reads the environment variable TUNNEL_TOKEN of the control node; never put the token into the inventory unencrypted. It is written to /etc/cloudflared/token (mode 0600, owner cloudflared_user) and never appears on a command line, in the unit or in Ansible output. |
| `cloudflared_user` | str | `cloudflared` | System user and group the connector runs as. Created without a home directory or login shell. |
| `cloudflared_metrics_address` | str | `127.0.0.1:2000` | host:port of the metrics and readiness listener (/metrics, /ready). Keep it on the loopback address or a private address; the role refuses an all-addresses listener. |
| `cloudflared_service_enabled` | bool | `true` | Enable and start the connector. With true, a start or restart waits until the tunnel has a connection (systemd Type=notify) and fails after 30 seconds without one. False installs and configures everything but keeps the service stopped and disabled. |
| `cloudflared_extra_args` | list of str | `[]` | Extra options of "cloudflared tunnel", placed before "run" (for example --protocol http2, --edge-ip-version 4 or --loglevel debug). Only letters, digits and . _ : / = @ , + - are allowed; --token and --metrics are refused (the role sets the token file and the metrics address). |
<!-- argument-specs:cloudflared:end -->

## Secrets

Secrets never go into this repository, an issue or a log. A role takes a secret only as a
variable (from Ansible Vault, a SOPS-encrypted vars file or an environment lookup in your own
inventory), never as a default value, and every task that handles a secret sets `no_log: true`.
CI scans every commit with gitleaks; a leaked secret is rotated first and removed from history
second.
