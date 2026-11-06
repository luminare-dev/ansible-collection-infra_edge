# luminare.infra_edge.mariadb

MariaDB from the distribution (11.8 on Debian 13, 10.11 on Ubuntu 24.04), secured like
`mysql_secure_installation` but without a root password (root keeps its `unix_socket` login),
tuned through one configuration file, with databases and accounts from a list and nightly zstd
dumps. It listens on `127.0.0.1` by default and can open port 3306 for application hosts in the
[`base`](../base/README.md) firewall.

## Requirements

- Debian 13 or Ubuntu 24.04, reached as root or with `become: true`.
- `ansible.mariadb` 6.x on the control node (a dependency of the collection).
- Account passwords from Ansible Vault or SOPS, never from a plain-text inventory.

## Example playbook

```yaml
- name: Run the database of the applications on this host
  hosts: edge
  become: true
  roles:
    - role: luminare.infra_edge.mariadb
      vars:
        mariadb_databases:
          - name: status
            user: status
            password: "{{ vault_status_db_password }}"
          - name: wiki
            user: wiki
            password: "{{ vault_wiki_db_password }}"
            priv: "wiki.*:SELECT,INSERT,UPDATE,DELETE,CREATE,ALTER,INDEX,DROP"
```

Applications connect over `/run/mysqld/mysqld.sock` or `127.0.0.1:3306` (host `localhost`
covers both).

## What it sets up

- Root only over the socket for the system's root user; anonymous accounts, the test database
  and remote root accounts are removed.
- `/etc/mysql/mariadb.conf.d/60-tuning.cnf`: bind address, `utf8mb4`, connections, InnoDB buffer
  pool (a share of the host's memory) and the slow query log.
- Databases and accounts from `mariadb_databases`; changed passwords and privileges are applied,
  nothing that leaves the list is dropped. Passwords never show in the output.
- Nightly dumps at 03:15 by a sandboxed systemd timer, see [Dumps](#dumps).

## Variables

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

## Tags

`mariadb`, `mariadb_install`, `mariadb_config`, `mariadb_service`, `mariadb_secure`,
`mariadb_databases`, `mariadb_dump`, `mariadb_firewall`. The input checks always run.

## Dumps

Every night `mariadb-dump.service` writes into `/var/backups/mariadb` (root only):

| File | Content |
|---|---|
| `<database>-20261021T031500Z.sql.zst` | one database, taken with `--single-transaction` |
| `system-users-20261021T031500Z.sql.zst` | every account with its password hash and grants |

Dumps older than `mariadb_dump_retention_days` (2) are deleted only after a run in which every
dump succeeded. Copy them off the host with a backup tool, for example
[`restic_backup`](../restic_backup/README.md).

```bash
systemctl start mariadb-dump.service      # run a dump now
zstd -dc /var/backups/mariadb/<database>-<time>.sql.zst | mariadb
zstd -dc /var/backups/mariadb/system-users-<time>.sql.zst | mariadb
```

## Application hosts

To serve applications on other hosts, listen on the private address and open 3306 for them:

```yaml
mariadb_bind_address: 192.0.2.10
mariadb_allowed_app_hosts:
  - 192.0.2.13
mariadb_databases:
  - name: app
    user: app
    host: 192.0.2.13
    password: "{{ vault_app_db_password }}"
```

The role writes `/etc/nftables.d/30-mariadb.nft` for them. Connections are not encrypted, so
keep them on a private network.

## Testing

```bash
cd roles/mariadb && export MOLECULE_ROLE=mariadb && molecule test
```

## Limitations

- No TLS on the server.
- Databases and accounts removed from the list stay on the server.
- Dumps are logical: large databases restore slowly, and non-InnoDB tables are not part of the
  consistent snapshot.
