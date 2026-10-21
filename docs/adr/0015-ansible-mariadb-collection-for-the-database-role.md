# 0015. ansible.mariadb for the database role instead of community.mysql or own SQL tasks

- **Status:** accepted
- **Date:** 2026-10-22

## Context

The `mariadb` role creates databases and accounts, sets passwords and privileges, and removes
anonymous accounts, the test database and root accounts for other hosts, on every run and with
`changed=0` on the second run. Debian 13 ships MariaDB 11.8 and Ubuntu 24.04 ships MariaDB 10.11.
The well-known modules for this were in `community.mysql`. Checked on Ansible Galaxy on
2026-10-21: `community.mysql` (highest version 5.0.2) is marked deprecated, and its last release
points to the `ansible.mysql` repository (5.2.0, for MySQL and MariaDB). `ansible.mariadb` was
copied from `ansible.mysql` for MariaDB only and released as 6.0.0, 6.0.1 and 6.0.2 on 2026-07-09
(6.0.2 needs ansible-core 2.16 or later). The `ansible` 14.5.0
package of the hash-pinned test toolchain ([ADR 0007](0007-one-hash-pinned-test-toolchain.md))
contains `ansible.mariadb` 6.0.2.

## Considered options

1. `ansible.mariadb` 6.x (`mariadb_db`, `mariadb_user`, `mariadb_info`, `mariadb_query`), logging in
   as root over the server's socket.
2. `community.mysql` 5.x.
3. `ansible.mysql`, the successor of `community.mysql` for MySQL and MariaDB.
4. Own tasks that run SQL with the `mariadb` client and parse its output.

## Decision

Option 1, with the version range `>=6.0.0,<7.0.0` in `galaxy.yml`. It is the collection made for
the server this role installs, it has a stable release, and the Molecule jobs get it from the
hash-pinned `ansible` package instead of Galaxy. Option 2 is deprecated. Option 3 serves MySQL and
MariaDB together, while its maintainers copied the MariaDB code into option 1 to develop it there
(the 6.0.0 changelog). Option 4 would re-implement the comparison of passwords and privileges
that the modules already do.

Every module call sets `login_unix_socket: /run/mysqld/mysqld.sock`, `login_user: root` and
`config_file: ""`: root keeps the packages' `unix_socket` login, so the role needs no root
password, and a `~/.my.cnf` of the remote user cannot change the login. The modules need PyMySQL
on the managed host, which the role installs from the distribution (`python3-pymysql`).

Tested on 2026-10-22 in the Molecule scenario on Debian 13 (MariaDB 11.8.6, PyMySQL 1.1.1) and
Ubuntu 24.04 (MariaDB 10.11.14, PyMySQL 1.0.2) with ansible.mariadb 6.0.2: converge, a second run
with `changed=0`, and the removal of planted anonymous accounts, a test database and remote root
accounts.

## Consequences

- Good: password and privilege changes are detected by the modules, so a changed value in the
  inventory is applied and an unchanged one reports no change.
- Good: no download from Galaxy in CI for this collection.
- Bad: `ansible.mariadb` is young (first release 2026-07-09) and its documentation still mentions
  MySQL in places; a breaking change would come with 7.0.0, which the range excludes.
- Bad: `mariadb_query` has no check mode, so the removal of the old `mysql.db` rows for test
  databases is skipped in check mode.
