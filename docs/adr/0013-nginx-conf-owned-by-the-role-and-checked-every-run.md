# 0013. nginx.conf owned by the role and checked on every run instead of a conf.d file and per-file checks

- **Status:** accepted
- **Date:** 2026-10-21

## Context

The `nginx` role needs settings at the `http` level (version hidden, client address from the
connector, JSON access log, gzip, security headers, websocket map) and, for relays, a `stream`
block, which must be in the main context of `/etc/nginx/nginx.conf`. The `nginx.conf` of the
Debian 13 and Ubuntu 24.04 packages already sets `gzip on` and an `access_log` in the combined
format at the `http` level and includes `conf.d/*.conf` and `sites-enabled/*` there; the Ubuntu
file also still allows TLS 1.0 and 1.1. A second `gzip` in a `conf.d` file is a duplicate
directive (nginx refuses to start), and a second `access_log` adds a second log instead of
replacing the first. Single files cannot be checked on their own: `nginx -t -c <file>` only works
for a complete main configuration. `systemctl reload nginx` fails on a configuration that nginx
cannot parse, but an error that only shows when nginx applies it (for example a port that another
process holds) is written to the error log while the reload reports success.

## Considered options

1. The role writes the whole `nginx.conf` (Debian's layout kept: `modules-enabled`, `conf.d`,
   `sites-available` and `sites-enabled`), writes every file first, runs `nginx -t` as a task on
   every run and reloads in a handler.
2. A `conf.d/00-hardening.conf` file plus line edits of the package's `nginx.conf`, with
   `nginx -t` in a handler before the reload.
3. A `validate:` check on each template.

## Decision

Option 1. The check is a task, not a handler, because a failed handler (a check or a reload)
loses its notification: the next run would see no change, skip the check and pass with the
broken files still on disk.
As a task it runs on every run, so the play keeps failing until the input is fixed, and the
reload handler only runs after a check that passed. The check is skipped in check mode, where no
file is written.

Option 2 has to edit a file that the package also changes, and the result differs between Debian
and Ubuntu. Option 3 cannot work for files that are only pieces of the configuration.

## Consequences

- Good: Debian 13 and Ubuntu 24.04 get the same main configuration, and the Molecule scenario
  checks it with `nginx -t` and `nginx -T` on both.
- Good: a broken input never reaches a running nginx through this role.
- Bad: local changes to `nginx.conf` are overwritten; extra `http` settings go into
  `/etc/nginx/conf.d/*.conf`. When a package update changes `nginx.conf`, dpkg asks which
  version to keep: a manual `apt upgrade` shows the question, and unattended-upgrades holds that
  update back until someone installs it by hand.
- Bad: after a failed check the new files stay on disk until the next run fixes them. If nginx is
  restarted in that window (for example by a reboot), it does not start, because the unit runs
  `nginx -t` before the start; the [runbook](../runbook.md) covers it.
