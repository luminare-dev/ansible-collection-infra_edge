# Configuration

Each role of the collection is configured through its own variables. Every variable starts with
the role name (for example `<role>_enabled`), has its default in `roles/<role>/defaults/main.yml`
and is described, with its type, in `roles/<role>/meta/argument_specs.yml`, which Ansible checks
when the role starts. Each role gets a section on this page with a table of its options (variable,
type, default, description), generated from that file with `python3 tests/role_docs.py --write`;
a unit test fails when a table here or in a role README is out of date.

## Playbook luminare.infra_edge.edge

[`luminare.infra_edge.edge`](../playbooks/edge.yml) runs the four roles below in this order:
`base`, `cloudflared`, `nginx`, `mariadb`. It has no variables of its own except the host pattern,
and passes nothing to the roles: every value comes from the inventory, as role variables.
[`examples/edge/`](../examples/edge/) is a complete inventory for one host (tested by the Molecule
scenario `edge`); a unit test fails when it sets a variable that none of the four roles has.

| Variable | Type | Default | Description |
|---|---|---|---|
| `edge_hosts` | str | `edge` | Host pattern of the play: an inventory group, a host or any pattern, for example `-e edge_hosts=web`. `--limit` narrows it further. |

Each role's tasks carry the role name as a tag, so `--skip-tags mariadb` runs the playbook
without the database role. With `--tags`, the input checks of all four roles still run (tag
`always`), so their required values (SSH keys, tunnel token, database passwords) must be set.

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

## nginx

[`luminare.infra_edge.nginx`](../roles/nginx/README.md) runs nginx as the reverse proxy behind the
tunnel: one site per application on a loopback listener, the client address from the connector's
`CF-Connecting-IP` header (trusted only from `127.0.0.1`), a JSON access log, no version in the
`Server` header, security headers, websockets and, optionally, TCP and UDP relays with the stream
module. Each item of `nginx_sites` needs `name`, `server_name` and `upstream`; `listen` defaults to
`127.0.0.1:8080` and must stay on a loopback address.

<!-- argument-specs:nginx:begin -->
| Variable | Type | Default | Description |
|---|---|---|---|
| `nginx_package` | str | `nginx` | Package that provides nginx (Debian 13 ships 1.26, Ubuntu 24.04 ships 1.24). |
| `nginx_sites` | list of dict | `[]` | Reverse proxy sites, one per application. Keys: name (file name in /etc/nginx/sites-available, lower-case letters, digits, - and _), server_name (one name or several separated by spaces), listen (a loopback address with a port, default 127.0.0.1:8080; other addresses are refused), upstream (http:// URL of the application) and websocket (true passes Upgrade requests through, default false). A site that the role wrote earlier and that is no longer in the list is removed. |
| `nginx_remove_default_site` | bool | `true` | Remove the package's default site (/etc/nginx/sites-enabled/default), which listens on port 80 of every address. |
| `nginx_real_ip_from` | list of str | `["127.0.0.1"]` | Addresses or networks whose nginx_real_ip_header is trusted as the client address. Only the tunnel connector on the same host belongs here; a request from any other address keeps its own address, whatever the header says. The same list decides whose X-Forwarded-Proto is passed on. |
| `nginx_real_ip_header` | str | `CF-Connecting-IP` | Request header that holds the client address (set by the tunnel connector). |
| `nginx_server_tokens` | str: `off`, `on` | `off` | "off" sends "Server: nginx" without the version, also on error pages. Quote the value in YAML. |
| `nginx_client_max_body_size` | str | `16m` | Largest request body nginx accepts (client_max_body_size, for example 16m or 1g). |
| `nginx_gzip` | bool | `true` | Compress text, JSON, JavaScript, XML and SVG responses of at least 256 bytes, also proxied ones. |
| `nginx_json_access_log` | bool | `true` | Write /var/log/nginx/access.log (and stream-access.log) as one JSON object per line. False uses nginx's combined format. The log holds client addresses; logrotate keeps 14 days. |
| `nginx_websocket_read_timeout` | str | `1h` | How long a proxied websocket may stay idle on sites with websocket true (proxy_read_timeout); other sites keep nginx's 60 seconds. |
| `nginx_security_headers` | dict | `{"X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN", "Referrer-Policy": "strict-origin-when-cross-origin"}` | Response headers (name: value) added to every response that does not already carry the header from the application, error pages included. No Strict-Transport-Security: TLS ends at the tunnel's edge, which sets it. Values must not contain double quotes, backslashes or $. |
| `nginx_stream_enabled` | bool | `false` | Install the stream module and relay the ports in nginx_stream_upstreams. False removes the relays from the configuration (the module package stays installed). |
| `nginx_stream_upstreams` | list of dict | `[]` | TCP and UDP relays of the stream module, for example to a game server on another host. Keys: name (lower-case letters, digits and _), listen (a port, or address:port), upstream (host:port) and protocols (list of tcp and udp, default [tcp]). A relay listens on a public address, so the role opens its ports in the firewall drop-in. |
| `nginx_firewall_manage` | bool | `false` | false writes /etc/nftables.d/20-nginx.nft only when /etc/nftables.d exists (the firewall of the base role); true also creates the directory (nftables and /etc/nftables.conf must exist). The file holds accept rules for the relay ports and is removed when there is no relay; a running nftables is restarted after a change. Sites listen on loopback addresses and need no rule. |
| `nginx_firewall_sources` | list of str | `["0.0.0.0/0", "::/0"]` | Source networks that may reach the relay ports (IPv4 and IPv6 CIDRs). 0.0.0.0/0 and ::/0 together mean everyone. An empty list writes no accept rule. |
<!-- argument-specs:nginx:end -->

## mariadb

[`luminare.infra_edge.mariadb`](../roles/mariadb/README.md) runs the distribution's MariaDB server:
root on `unix_socket` login without a password, anonymous accounts, the test database and remote
root accounts removed, a tuning file (bind address `127.0.0.1` by default, character set, InnoDB
sizes, connections, slow query log), the databases and accounts of `mariadb_databases`, nightly
zstd dumps per database into `/var/backups/mariadb` with a retention in days, and optionally port
3306 for application hosts in the firewall drop-in directory of the base role. An item of
`mariadb_databases` with a `user` also needs its `password` (from Ansible Vault or SOPS).

<!-- argument-specs:mariadb:begin -->
| Variable | Type | Default | Description |
|---|---|---|---|
| `mariadb_packages` | list of str | `["mariadb-server", "python3-pymysql", "zstd"]` | Packages to install: the server (MariaDB 11.8 on Debian 13, 10.11 on Ubuntu 24.04), the Python driver that the ansible.mariadb modules need on the host, and zstd for the dumps. Add packages, do not remove these. |
| `mariadb_bind_address` | str | `127.0.0.1` | The one IPv4 or IPv6 address the server listens on (port 3306). The default keeps it on the host; set a private address for application hosts and list them in mariadb_allowed_app_hosts. The socket /run/mysqld/mysqld.sock always works. |
| `mariadb_databases` | list of dict | `[]` | Databases and their accounts. Keys: name (database; letters, digits and _), user and password (optional account; both or neither), host (where the account may connect from, default localhost, the socket) and priv (privileges in the ansible.mariadb.mariadb_user format, default all privileges on its own database, for example app.*:ALL for the database app). A changed password or priv is applied on the next run. Databases and accounts that leave the list are not dropped. |
| `mariadb_innodb_buffer_pool_ratio` | float | `0.25` | Share of the host's memory for the InnoDB buffer pool, used by the default of mariadb_innodb_buffer_pool_size (0.25 when the host also runs applications; 0.5 to 0.7 on a host for the database only; at most 0.9). |
| `mariadb_innodb_buffer_pool_size` | str | `{{ (ansible_facts['memtotal_mb'] * mariadb_innodb_buffer_pool_ratio) \| int }}M` | Size of the InnoDB buffer pool (a number with K, M or G). The default is the host's memory times mariadb_innodb_buffer_pool_ratio. |
| `mariadb_innodb_log_file_size` | str | `256M` | Size of the InnoDB redo log (a number with K, M or G). |
| `mariadb_max_connections` | int | `100` | Most client connections at the same time. |
| `mariadb_character_set_server` | str | `utf8mb4` | Character set of new databases and tables. |
| `mariadb_collation_server` | str | `""` | Collation of new databases and tables. Empty keeps the package's utf8mb4 collation (utf8mb4_uca1400_ai_ci on Debian 13, utf8mb4_general_ci on Ubuntu 24.04); another character set needs a collation of that set here. |
| `mariadb_slow_query_log` | bool | `true` | Log statements that run longer than mariadb_long_query_time to /var/log/mysql/mariadb-slow.log (the statements' text; rotated by the package's logrotate rule). |
| `mariadb_long_query_time` | float | `1` | Seconds after which a statement counts as slow. |
| `mariadb_dump_enabled` | bool | `true` | Run the dump timer. False stops and disables it; the script and the service stay, so a dump can still be started by hand, and existing dumps are kept. |
| `mariadb_dump_dir` | str | `/var/backups/mariadb` | Folder of the dumps (owner root, mode 0700). Every file in it that ends in .sql.zst counts as a dump for the retention. |
| `mariadb_dump_oncalendar` | str | `*-*-* 03:15:00` | When the dumps run (systemd OnCalendar expression, local time of the host). A run missed while the host was off follows at the next boot. |
| `mariadb_dump_retention_days` | int | `2` | Days a dump is kept. After a successful run, dumps older than this are deleted; a failed run deletes nothing. |
| `mariadb_allowed_app_hosts` | list of str | `[]` | IPv4 and IPv6 addresses or CIDRs of the application hosts that may reach port 3306 through the firewall of the base role (never /0). The server must also listen on an address they reach (mariadb_bind_address), and their accounts need a matching host. |
| `mariadb_firewall_manage` | bool | `false` | false writes /etc/nftables.d/30-mariadb.nft only when /etc/nftables.d exists (the firewall of the base role); true also creates the directory (nftables and /etc/nftables.conf must exist). The file holds accept rules for port 3306 from mariadb_allowed_app_hosts and is removed when the list is empty; a running nftables is restarted after a change. |
<!-- argument-specs:mariadb:end -->

## Secrets

Secrets never go into this repository, an issue or a log. A role takes a secret only as a
variable (from Ansible Vault, a SOPS-encrypted vars file or an environment lookup in your own
inventory), never as a default value, and every task that handles a secret sets `no_log: true`.
CI scans every commit with gitleaks; a leaked secret is rotated first and removed from history
second.
