# 0008. SSH hardening through devsec.hardening instead of an own sshd drop-in

- **Status:** accepted; amends [ADR 0007](0007-one-hash-pinned-test-toolchain.md) (one collection
  from Ansible Galaxy)
- **Date:** 2026-10-21

## Context

The `base` role must leave every host with key-only SSH logins, no root login, logins limited to
the `sshusers` group and `MaxAuthTries 3`, on Debian 13 and Ubuntu 24.04, with a second run
reporting `changed=0`. `devsec.hardening.ssh_hardening` is a widely used role for exactly this
and also maintains the algorithm lists per OpenSSH version, the host key sizes, the client
configuration and the Ubuntu socket activation. The alternative is an own drop-in
`/etc/ssh/sshd_config.d/10-hardening.conf`, which leaves the distribution's `sshd_config` alone.
No role of this collection, and no role planned for the projects that use it, adds files to
`/etc/ssh/sshd_config.d/`: users that other roles need (for example a deploy user) join the
`sshusers` group, and per-key restrictions go into `authorized_keys`.

## Considered options

1. Wrap `devsec.hardening.ssh_hardening` (version range `>=11.0.0,<12.0.0`) and pass the
   required settings as role parameters.
2. An own drop-in in `/etc/ssh/sshd_config.d/` with only the required settings.
3. Both: devsec for the main file plus an own drop-in.

## Decision

Option 1. `tasks/ssh.yml` includes `devsec.hardening.ssh_hardening` with the port, listen
addresses, `PermitRootLogin no`, password and keyboard-interactive login off,
`AuthenticationMethods publickey`, `AllowGroups <base_ssh_group>` and `MaxAuthTries` as role
parameters, which inventory variables cannot override; every other devsec variable stays
available. Option 2 would re-implement what devsec already maintains, and a drop-in only
works while the main file keeps its `Include` line and no earlier drop-in (for example one
from cloud-init) sets the same option first. Option 3 does not work: devsec's `sshd_config`
has no `Include`, so a drop-in would not be read.

Tested on 2026-10-21 in the Molecule scenario on Debian 13 and Ubuntu 24.04 with
devsec.hardening 11.0.0: converge, a second run with `changed=0`, and SSH logins to the
container: key logins of the two users succeed, root (put into `sshusers` by the test) and a
user outside `sshusers` are refused with a valid key, password logins are refused. The same
scenario passed with ansible-core 2.20.10 and 2.21.5.

`galaxy.yml` lists `devsec.hardening: ">=11.0.0,<12.0.0"`, and the scenario's
`requirements.yml` installs the same range from Ansible Galaxy: devsec.hardening is not part of
the hash-pinned `ansible` package of the test toolchain, so it is the one exception to
[ADR 0007](0007-one-hash-pinned-test-toolchain.md). Its own dependencies (`ansible.posix`,
`community.crypto`, `community.general`, `community.mysql`) come from that package. ansible-lint
runs with `--offline`, so the required `ci / lint-test` check does not download devsec.hardening.

## Consequences

- Good: the SSH settings follow devsec's reviewed defaults and their updates; the role only
  pins what this collection promises.
- Good: `sshd_config` is validated with `sshd -T` before it is replaced, and drop-ins from other
  packages cannot weaken it.
- Bad: devsec owns the whole `sshd_config`; options outside its variables need its
  `sshd_custom_options`. Its defaults also turn TCP and agent forwarding off, and on its first
  run it replaces a smaller RSA host key with a 4096-bit key (the fingerprint changes). Both are
  documented in the role README.
- Bad: the Molecule jobs download devsec.hardening from Galaxy within a version range instead
  of a hash-pinned file; a broken 11.x release would show in the weekly Molecule run first, and
  a Galaxy outage fails the `molecule` check, which is not a required check.
