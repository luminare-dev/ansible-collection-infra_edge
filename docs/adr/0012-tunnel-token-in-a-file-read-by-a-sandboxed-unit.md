# 0012. Tunnel token in a file read by a sandboxed unit instead of "cloudflared service install"

- **Status:** accepted
- **Date:** 2026-10-21

## Context

A remotely managed tunnel needs only one secret on the host: the tunnel token. Cloudflare's
quick setup is `cloudflared service install <token>`. The token is then on the command line of
that call, and releases before 2026.7.2 also wrote it into the `ExecStart` line of the unit,
where `ps`, `systemctl status` and `systemctl cat` show it to every local user (2026.7.2 and
later write it to `/etc/cloudflared/token`). That installer runs the service as root without a sandbox and adds a daily
self-update timer. Edge hosts may come from cloud-init with exactly this setup.

## Considered options

1. The role writes the token to `/etc/cloudflared/token` (mode 0600, owner `cloudflared`,
   directory `root:cloudflared` 0750) and its own unit runs
   `cloudflared --no-autoupdate tunnel --metrics <address> run --token-file /etc/cloudflared/token`
   as the system user `cloudflared` in a systemd sandbox.
2. The role calls `cloudflared service install` with the token.
3. The token in an `EnvironmentFile` (`TUNNEL_TOKEN=…`).

## Decision

Option 1. The token reaches the host only through a `copy` task with `no_log` and without diff;
the variable is marked `no_log` in the argument spec, and its default reads `TUNNEL_TOKEN` from
the control node's environment, so it does not have to be in the inventory. The unit uses the
same path as the installer, `/etc/systemd/system/cloudflared.service`, so the role takes over a
connector set up with option 2 and removes the installer's self-update units. The unit has
`Type=notify` (systemd waits for the first connection to the edge), no capabilities,
`NoNewPrivileges`, `ProtectSystem=strict`, private `/tmp` and `/dev`, kernel and control group
protection, `MemoryDenyWriteExecute`, a system call filter and only the address families
`AF_INET`, `AF_INET6`, `AF_UNIX` and `AF_NETLINK`. The metrics listener is set explicitly
(default `127.0.0.1:2000`), because without `--metrics` cloudflared picks a port itself and, in
some environments, listens on all addresses.

Option 2 puts the token on a command line and creates a root service that updates itself past
the pin (ADR 0011). Option 3 keeps the token out of the command line, but every child process
inherits the environment.

## Consequences

- Good: in the Molecule scenario, `systemctl cat`, `systemctl show`, the process command line
  and the journal contain no token, while the journal shows the tunnel ID from the token, so the
  service user read the token file under the sandbox.
- Good: a wrong token or a blocked outbound port fails the start or restart (no readiness within
  30 seconds) instead of leaving a service that looks active.
- Bad: root on the host can still read the token; a host compromise means rotating the token in
  the Cloudflare dashboard.
- Bad: the readiness wait cannot be tested in a container without a real tunnel; the Molecule
  scenario overrides it (see the role README).
