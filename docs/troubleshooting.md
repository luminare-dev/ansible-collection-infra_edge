# Troubleshooting

## Could not find git executable to extract the collection from the Git repository

```text
[ERROR]: Could not find git executable to extract the collection from the Git repository
`https://github.com/luminare-dev/ansible-collection-infra_edge.git`: Failed to find required
executable "git" in paths: ...
```

**Cause:** `ansible-galaxy` clones the repository to install from a tag, and git is not
installed on the control node.

**Fix:** install git, or install the collection tarball from the GitHub release instead (see
[Installation](install.md)).

```bash
sudo apt-get install git
```

## The role 'luminare.infra_edge.…' was not found

```text
[ERROR]: The role 'luminare.infra_edge.<role>' was not found in: ...
```

**Cause:** the collection is not installed in a path that `ansible-playbook` searches, or it is
installed in another virtual environment or user account.

**Fix:** check where the collection is, and install it again in the same environment that runs
the playbook.

```bash
ansible-galaxy collection list luminare.infra_edge
ansible-config dump | grep COLLECTIONS_PATHS
```

## The playbook luminare.infra_edge.edge could not be found

```text
[ERROR]: the playbook: luminare.infra_edge.edge could not be found
```

**Cause:** the collection is not installed in a path that `ansible-playbook` searches (see the
previous entry), or an older version without the playbook is installed there.

**Fix:** check the version with `ansible-galaxy collection list luminare.infra_edge`, and install
the collection again in the environment that runs the playbook.

## The edge playbook stops with "'vault_edge_app_db_password' is undefined"

**Cause:** the example inventory takes the admin password hash and the two database passwords
from `group_vars/edge/vault.yml`, and that file does not exist, misses the value, or was not
decrypted (no `--ask-vault-pass` or vault password file).

**Fix:** create the file with `ansible-vault create group_vars/edge/vault.yml` next to
`main.yml`, with `vault_base_admin_password_hash`, `vault_edge_app_db_password` and
`vault_edge_app_reader_db_password` (see the [example's README](../examples/edge/README.md)), and
run the playbook with `--ask-vault-pass`.

## The second run of the edge playbook cannot log in as root

```text
root@203.0.113.10: Permission denied (publickey).
```

**Cause:** the first run logged in as root, and the base role then refused SSH logins as root
(`PermitRootLogin no`). This is intended.

**Fix:** set `ansible_user: ansible` (the automation user, `base_automation_user`) for the host in
the inventory; it logs in with one of the keys in `base_automation_ssh_keys` and uses sudo without
a password.

## The base role stops with "Set base_admin_ssh_keys and base_automation_ssh_keys"

**Cause:** one of the two key lists is empty, or both users have the same name. The SSH server
accepts keys only, so a user without a key could not log in; the role stops before it changes
anything.

**Fix:** set at least one public key for each user in the inventory (`base_admin_ssh_keys`,
`base_automation_ssh_keys`), and give the users different names.

## The base role stops with "base_mgmt_cidrs is empty"

**Cause:** `base_ssh_allow_mode` is `mgmt_cidrs` (the default), but no management network is
listed, so the firewall would refuse SSH from every address.

**Fix:** list the networks you administer the host from (for example `192.0.2.0/24`), or set
`base_ssh_allow_mode: any` (SSH open to everyone, protected by keys and fail2ban) or `loopback`
(only local or tunnelled access).

## The base role stops with "is not a valid host name"

**Cause:** `base_hostname` defaults to the inventory name of the host. If the inventory names
the host by its IP address (for example `203.0.113.10`) or the name contains characters a host
name may not have (such as `_`), the role refuses it before it changes anything, because the name
would end up in `/etc/hosts` or make `hostnamectl` fail.

**Fix:** set `base_hostname` for the host to a valid name (for example `edge-1` or
`edge-1.example.com`), or to `""` to leave the host name and `/etc/hosts` unchanged.

## The cloudflared role stops with "Set cloudflared_token"

**Cause:** `cloudflared_token` is empty (by default it is read from the environment variable
`TUNNEL_TOKEN` of the control node, and that variable is not set in the shell that runs
`ansible-playbook`), or the value is not a tunnel token. A tunnel token is base64-encoded JSON and
starts with `eyJ`; the tunnel ID or an API token does not work. The edge playbook also stops here
when it runs with `--tags` for another role, because the input checks of all four roles run with
every tag; leave roles out with `--skip-tags` instead, or export the token.

**Fix:** copy the token of the remotely managed tunnel from the Cloudflare dashboard (it is part
of the install command shown for the tunnel) and export it without echo in the same shell:

```bash
read -rs TUNNEL_TOKEN && export TUNNEL_TOKEN
```

## The cloudflared role fails at "Download the package file and check its SHA-256"

**Cause:** `cloudflared_version` was changed without `cloudflared_deb_sha256` (the checksum does
not match the new file), or the version does not exist in Cloudflare's repository pool.

**Fix:** take both SHA-256 values (`cloudflared-linux-amd64.deb`, `cloudflared-linux-arm64.deb`)
from the checksum list of the same GitHub release and set them together with the version (see
"Upgrading cloudflared" in the [role README](../roles/cloudflared/README.md#upgrading-cloudflared)).

## The cloudflared role fails at "Enable and start the connector" or "Restart cloudflared"

**Cause:** the unit has `Type=notify`, so systemd waits for the tunnel's first connection to
Cloudflare's edge and gives up after 30 seconds: the token is wrong or was rotated, or outbound
port 7844 is blocked.

**Fix:** read the reason with `journalctl -u cloudflared -n 50` on the host, then follow
"Tunnel connector down" in the [runbook](runbook.md).

## The nginx role stops with "Every item of nginx_sites needs a unique name"

**Cause:** an item of `nginx_sites` breaks a rule that the role checks before it changes
anything: the `listen` address is not on the loopback interface (only `127.0.0.1:<port>` or
`[::1]:<port>`; the tunnel connector on the same host is the only client), the `upstream` is not
an `http://` URL, the name is used twice or is `default`, or a value contains a space, quote,
semicolon or brace. The message lists the site names it read.

**Fix:** correct the item. A site for another host needs that host's own nginx and connector.

## The nginx role fails at "Check the configuration with nginx -t"

**Cause:** the role wrote the files, but nginx refuses the configuration, for example because the
host name in an `upstream` does not resolve on the host (nginx resolves it when it loads the
configuration: `host not found in upstream`), or because of a file in `/etc/nginx/conf.d/` that
the role does not manage. nginx keeps serving the configuration it had before; the role does not
reload it.

**Fix:** read the message of the failed task (nginx names the file and line), correct the
inventory or the other file, and run the playbook again. Until then every run fails at this
check.

## A relay port of the nginx role is not reachable from other hosts

**Cause:** the firewall of the base role has no rule for it: `/etc/nftables.d` did not exist
when the role ran (and `nginx_firewall_manage` is false), nftables was not running, so the role
did not restart it, or `nginx_firewall_sources` does not cover the client. A firewall in front of
the host (for example at the hosting provider) can also block it.

**Fix:** check the rules with `cat /etc/nftables.d/20-nginx.nft` and
`nft list chain inet filter input`, and the listener with `ss -tulnp | grep nginx`. Apply the
base role before the nginx role (or set `nginx_firewall_manage: true`), correct
`nginx_firewall_sources`, and run the playbook again.

## The mariadb role stops with "Every item of mariadb_databases needs a name"

**Cause:** an item of `mariadb_databases` breaks a rule that the role checks before it changes
anything: the database name has a character other than letters, digits and `_`, or is `test`,
`mysql` or another system database; `user` and `password` are not given together; the user is
`root`, `mysql` or `mariadb.sys`; or the same user and host appear twice. The message lists the
databases and accounts it read, never a password.

**Fix:** correct the item, for example with `_` instead of `-` or `.` in a database name.

## The mariadb role stops with "mariadb_bind_address must be one IPv4 or IPv6 address of this host"

**Cause:** the address is not one of the host's addresses (the server would not start on it), or
it is written with a port or a prefix length. The message lists the addresses the host has.

**Fix:** use one address from the list exactly as written there, `127.0.0.1` (the default), or
`0.0.0.0` for every IPv4 address (then limit the access with `mariadb_allowed_app_hosts` and the
base firewall).

## The mariadb role fails at "Remove the anonymous accounts" with "unable to connect to database"

The message of the failed task contains `Access denied for user 'root'@'localhost'`.

**Cause:** root no longer logs in with `unix_socket`, for example because someone set a root
password with `ALTER USER` or chose one in `mysql_secure_installation`. The role logs in as root
over the socket without a password.

**Fix:** on the host, log in with that password and give root its `unix_socket` login back, then
run the playbook again:

```bash
mariadb -u root -p -e "ALTER USER root@localhost IDENTIFIED VIA unix_socket"
```

## Application hosts cannot reach the database

**Cause:** the server listens on `127.0.0.1` (the default `mariadb_bind_address`), the base
firewall has no rule for the client (`mariadb_allowed_app_hosts` empty, or `/etc/nftables.d` did
not exist when the role ran and `mariadb_firewall_manage` is false), or the account's `host` does
not match the client's address (`Access denied for user 'app'@'192.0.2.13'`).

**Fix:** check the listener with `ss -tlnp | grep mariadbd`, the rule with
`cat /etc/nftables.d/30-mariadb.nft` and `nft list chain inet filter input`, and the accounts with
`mariadb -e "SELECT User, Host FROM mysql.user"`. Set `mariadb_bind_address`,
`mariadb_allowed_app_hosts` and the account's `host` together (see
[Application hosts](../roles/mariadb/README.md#application-hosts)) and run the playbook again.

## The restic_backup role stops with "Set restic_backup_repository"

**Cause:** `restic_backup_repository` or `restic_backup_password` is empty (the defaults), the
repository is not an absolute path or `<backend>:<location>` of a restic backend, or one of them
contains a space or a line break. With the edge playbook this happens when
`edge_restic_backup_enabled` is true and the inventory has no repository for the host.

**Fix:** set both for the host, the password from the vault file, for example
`restic_backup_repository: s3:https://s3.example.com/edge-backups/edge-01` in the inventory, or
set `edge_restic_backup_enabled: false` to leave the backups out.

## The restic_backup role stops with "The repository exists, but restic_backup_password does not open it"

**Cause:** the repository at `restic_backup_repository` was created with another password, or the
address points to the repository of another host. The role tried the new settings before writing
them, so the settings on the host and a running backup job are unchanged.

**Fix:** put the password the repository was created with into the vault file. To change the
password of a repository, add a key with the new password first (`restic-env key add`), then
change the vault value and run the playbook, then remove the old key (`restic-env key list`,
`restic-env key remove <id>`).

## The restic_backup role stops with "restic cannot open the repository"

**Cause:** restic could not reach the backend or was refused by it: a wrong address, wrong or
missing credentials in `restic_backup_env`, a firewall on the way, or a backend that is down. The
message ends with restic's own error. The settings on the host were not changed.

**Fix:** check the address and the credentials, and try them by hand in a root shell on the
host: export the backend's variables (for example `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY`), then run `restic -r <repository> cat config` and enter the password. For
an SFTP server, add the server's host key to `/root/.ssh/known_hosts` and the client key to
`/root/.ssh` first: restic cannot answer the SSH host key question.

## restic-backup.service fails with "these paths do not exist"

**Cause:** a path of `restic_backup_paths` is missing on the host, for example
`/var/backups/mariadb` on a host without the `mariadb` role. The script stops before restic runs,
so the status file keeps the last successful time.

**Fix:** remove the path from `restic_backup_paths` (the default `/var/backups` covers the dumps
of `mariadb` on hosts that have it) or create it, then start the service again.

## The role 'devsec.hardening.ssh_hardening' was not found

```text
[ERROR]: The role 'devsec.hardening.ssh_hardening' was not found in: ...
```

**Cause:** the collection was installed with `--no-deps` or from a copy, so its dependencies
(`devsec.hardening`, `community.general`, `ansible.posix`, `ansible.mariadb`) are missing. The
same applies to `couldn't resolve module/action 'ansible.mariadb.mariadb_user'`.

**Fix:** install them, or install the collection again without `--no-deps`.

```bash
ansible-galaxy collection install "devsec.hardening:>=11.0.0,<12.0.0" "community.general:>=13.0.0,<14.0.0" "ansible.posix:>=2.2.0,<3.0.0" "ansible.mariadb:>=6.0.0,<7.0.0"
```

## Molecule: docker command not found in PATH

```text
[ERROR]: Task failed: docker command not found in PATH: Failed to find required executable
"docker" in paths: ...
```

**Cause:** the instances are created through the Docker API, but Ansible connects to them with
the `community.docker.docker` connection plugin, which calls the Docker command-line client.

**Fix:** install the Docker client on the machine that runs Molecule (the GitHub runners have it).

```bash
sudo apt-get install docker.io
```

## Still stuck?

Search the issues, then ask in the project's
[Discussions](https://github.com/luminare-dev/ansible-collection-infra_edge/discussions). Never
post secrets, keys, IP addresses, hostnames or personal data; redact logs before you paste them.
