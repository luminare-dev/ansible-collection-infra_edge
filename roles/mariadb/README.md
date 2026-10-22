# luminare.infra_edge.mariadb

Database server for a Debian 13 or Ubuntu 24.04 edge host: MariaDB from the distribution (11.8 on
Debian 13, 10.11 on Ubuntu 24.04), secured the way `mysql_secure_installation` does it but without
a root password (root keeps its `unix_socket` login), tuned through one configuration file, with
the databases and accounts from a list and nightly dumps: one zstd file per database plus one with
the accounts, kept for two days. The server listens on `127.0.0.1` by default; for application
hosts on other machines the role can open port 3306 for them in the firewall of the
[`base`](../base/README.md) role. The accounts and databases are managed with the
`ansible.mariadb` collection ([ADR 0015](../../docs/adr/0015-ansible-mariadb-collection-for-the-database-role.md)).

## Requirements

- Managed host: Debian 13 or Ubuntu 24.04 with systemd and Python 3, reached as root or with
  `become: true`. The role stops before any change on another distribution.
- The distribution's package mirror: the role installs `mariadb-server`, `python3-pymysql` (the
  driver that the `ansible.mariadb` modules use on the host) and `zstd`.
- Control node: ansible-core 2.20 or later and the `ansible.mariadb` collection 6.x (a dependency
  of this collection; it is also part of the `ansible` community package).
- Passwords of the accounts from an encrypted source (Ansible Vault or a SOPS-encrypted vars file),
  never from a plain-text inventory.
- For application hosts on a host with the [`base`](../base/README.md) firewall: the role writes
  port 3306 for them into `/etc/nftables.d/30-mariadb.nft`.

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

The applications connect over the socket `/run/mysqld/mysqld.sock` or to `127.0.0.1:3306` with
their account (host `localhost` covers both). For a database host that serves application hosts
on a private network, see [Application hosts](#application-hosts).

## What the role does

| Control | How | Checked in Molecule |
|---|---|---|
| No root password | root keeps the packages' `unix_socket` login: only the operating system's root user gets in, over the socket; the role and the dump service log in that way and need no password file | root over the socket works; root over TCP is refused; `SHOW GRANTS` shows `unix_socket` |
| `mysql_secure_installation` equivalent | anonymous accounts removed, the `test` database dropped and the old `mysql.db` rows that open every `test_…` database removed, root accounts for any host other than `localhost` (also `127.0.0.1`, `::1` and `%`) removed; on every run | after planting two anonymous accounts, a `test` database, an orphaned `mysql.db` row for `test\_%` and `root@%` and `root@127.0.0.1` with a password, the next run removes all of them and root with that password is refused over TCP |
| Network | `bind-address` (default `127.0.0.1`) in `/etc/mysql/mariadb.conf.d/60-tuning.cnf`, read after the package's `50-server.cnf` | `ss`: `mariadbd` listens on `127.0.0.1:3306` only; after the change to the instance's address, on that address only |
| Tuning | the same file sets the character set (`utf8mb4`), `max_connections` 100, the InnoDB buffer pool (host memory × `mariadb_innodb_buffer_pool_ratio`, 0.25 by default), a 256 MB redo log and the slow query log (statements over 1 second, `/var/log/mysql/mariadb-slow.log`); a change restarts the server and checks that it runs again | the server's values of all settings; a 1.2-second statement appears in the slow query log |
| Databases and accounts | `mariadb_databases` creates each database and, with `user` and `password`, an account with `priv` (default: everything on its database); a changed password or `priv` is applied on the next run; nothing that leaves the list is dropped. Every task that passes a password has `no_log`, and `password` is marked `no_log` in the argument specification | the account logs in with its password and works on its database, is refused on another database and with a wrong password; a second account from another host reads but cannot write; the password and its hash appear nowhere in the output of a converge with `-vvv` |
| Nightly dumps | `mariadb-dump.timer` (03:15, `Persistent=true`) starts `mariadb-dump.service`, which runs `/usr/local/sbin/mariadb-dump-all` as root in a sandbox (no capabilities, no network, read-only system except the dump folder): one `<database>-<UTC time>.sql.zst` per database and `system-users-<UTC time>.sql.zst` with the accounts and grants in `/var/backups/mariadb` (mode 0700, files 0600), then dumps older than 2 days are deleted, only after a run without errors (see [Dumps](#dumps)) | the timer is enabled, active and persistent; a run of the service writes the three non-empty files, deletes a planted 3-day-old dump and keeps one from yesterday; the database dump brings back a dropped table and the accounts dump a dropped account (it logs in with its password again); `systemd-analyze security` rates the service 1.3 |
| Firewall for application hosts (optional) | when `/etc/nftables.d` exists (or with `mariadb_firewall_manage: true`, which also creates it): `30-mariadb.nft` with `add rule inet filter input … tcp dport 3306 accept` lines for `mariadb_allowed_app_hosts`, checked together with `/etc/nftables.conf` by `nft --check` before it replaces the old file; a running nftables is restarted (a running fail2ban after it); the file is removed when the list is empty; `/0` is refused | converge without the directory: the role leaves the firewall alone; after the change: directory, file and content; the loaded input chain accepts port 3306 from the listed networks and keeps `policy drop` |
| Checked before any change | the database, account and host names, addresses, sizes, paths and the timer's calendar expression must match strict patterns (they end up in configuration files, a unit file and a shell script); `systemd-analyze calendar` checks the expression | the role's own runs; the patterns also have unit tests |

## Variables

The table is generated from [`meta/argument_specs.yml`](meta/argument_specs.yml), which Ansible
also uses to check the variables when the role starts, including the keys of every item of
`mariadb_databases`.

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

`mariadb` (every task) and one tag per part: `mariadb_install`, `mariadb_config`,
`mariadb_service`, `mariadb_secure`, `mariadb_databases`, `mariadb_dump`, `mariadb_firewall`. The
checks at the start always run.

## Dumps

Every night at 03:15 (local time of the host), `mariadb-dump.service` writes into
`/var/backups/mariadb`:

| File | Content |
|---|---|
| `<database>-20261021T031500Z.sql.zst` | one database: `CREATE DATABASE`, tables, data, routines, events and triggers, taken with `--single-transaction` (a consistent snapshot of InnoDB tables without locking them) |
| `system-users-20261021T031500Z.sql.zst` | every account with its password hash and grants (`CREATE USER IF NOT EXISTS …` and `GRANT …`) |

The system databases (`mysql`, `information_schema`, `performance_schema`, `sys`) are not dumped
one by one; the accounts file covers what matters in `mysql`. A file is written as `.partial` and
renamed when its dump and compression succeeded. Files older than `mariadb_dump_retention_days`
(2) are deleted after a run in which every dump succeeded, so a failing run keeps the older dumps.
The files hold all data and the password hashes: only root can read them. The dumps stay on the
host; copy them off the host with a backup tool (for example restic) after 03:15.

Run a dump by hand and look at the result:

```bash
systemctl start mariadb-dump.service
journalctl -u mariadb-dump.service -n 5
ls -l /var/backups/mariadb
```

Restore one database from its dump (the dump recreates the database if it is missing and replaces
its tables), and the accounts if they are missing:

```bash
zstd -dc /var/backups/mariadb/<database>-<time>.sql.zst | mariadb
zstd -dc /var/backups/mariadb/system-users-<time>.sql.zst | mariadb
```

## Application hosts

A database host for applications on other hosts listens on its private address and opens port
3306 for those hosts only:

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

The account's `host` limits where it may log in from, the firewall drop-in limits who reaches the
port at all. The connection is not encrypted, so keep it on a private network.

## Testing

`molecule/default` converges the role on Debian 13 and Ubuntu 24.04 (systemd containers), runs it
a second time and expects `changed=0`, then checks the controls in the table above.
`prepare.yml` loads a firewall in the base role's layout (input policy drop, include of
`/etc/nftables.d`, but without the directory) into the instance's own network namespace.
`converge.yml` applies the role with the defaults (`127.0.0.1`, dumps on, no application hosts)
and two databases, one with an account; a buffer pool ratio of 0.02 keeps the containers small.
`verify.yml` checks the server, the accounts, the slow query log, a dump run with its retention and
restores of a database and of the accounts. `side_effect.yml` then plants what
`mysql_secure_installation` removes and applies the role for application hosts (the instance's
own address, a second account from that address, `mariadb_firewall_manage: true`, dumps off), and
`verify_app_hosts.yml` checks the result.

```bash
cd roles/mariadb && export MOLECULE_ROLE=mariadb && molecule test
```

## Limitations

- Connections are not encrypted: the server has no TLS certificate, so accounts for other hosts
  belong on a private network.
- Every process of the host's root user can log in as the database root over the socket; that is
  the point of `unix_socket`. Other local users cannot.
- Databases and accounts that leave `mariadb_databases` stay on the server; drop them by hand.
- The dumps are logical dumps: a restore of a large database takes longer than a physical backup
  (for example `mariadb-backup`), and the dump is taken while the server keeps running, so
  non-InnoDB tables (MyISAM) are not part of the consistent snapshot.
- Only database names of letters, digits and `_` can be created by the role; an existing database
  with other characters is still dumped, with every other character replaced by `_` in its file
  name.
- The firewall restart was tested in the network namespace of a container. That port 3306 is
  reachable from an application host and closed to others is still to be checked on a virtual
  machine.
- Check mode on a host without the packages only reports the installation; the rest of the role
  needs a running server.
- Only x86_64 is tested.
