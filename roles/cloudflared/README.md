# luminare.infra_edge.cloudflared

Connector for a remotely managed Cloudflare Tunnel on a Debian 13 or Ubuntu 24.04 edge host: a
pinned cloudflared version, installed from its package file after a SHA-256 check and held with
an apt pin; the tunnel token in a file that only the service user can read; and a sandboxed
systemd service that reads the token from that file and keeps its metrics listener on the
loopback address. The host needs no open inbound port: the connector only opens outbound
connections to Cloudflare's edge (port 7844, QUIC over UDP or HTTP/2 over TCP), which the
[`base`](../base/README.md) firewall allows (its output policy is accept).

## Requirements

- Managed host: Debian 13 or Ubuntu 24.04 on x86_64 or aarch64 (only x86_64 is tested), with
  systemd and Python 3, reached as root or with `become: true`. The role stops before any change
  on another distribution or architecture.
- Outbound HTTPS to `pkg.cloudflare.com` (package file and apt repository) and outbound port 7844
  (UDP and TCP) to Cloudflare's edge.
- A remotely managed tunnel and its token. The token is part of the install command that the
  Cloudflare dashboard shows for the tunnel, and the API returns it
  (`GET /accounts/<account_id>/cfd_tunnel/<tunnel_id>/token`). Public hostnames and their
  services are configured on the tunnel in Cloudflare, not on the host.
- Control node: ansible-core 2.20 or later. The role uses only `ansible.builtin` modules.

## Example playbook

```yaml
- name: Run the tunnel connector
  hosts: edge
  become: true
  roles:
    - role: luminare.infra_edge.cloudflared
```

The token comes from the environment of the control node by default. Read it without echo, so
that it does not end up in the shell history:

```bash
read -rs TUNNEL_TOKEN && export TUNNEL_TOKEN
ansible-playbook -i inventory.yml edge.yml
```

To keep it in the inventory instead, set `cloudflared_token: "{{ vault_cloudflared_token }}"`
with the value in Ansible Vault or a SOPS-encrypted file.

## What the role does

| Control | How | Checked in Molecule |
|---|---|---|
| Known version, checked file | `cloudflared_version` (2026.10.2) is installed from `cloudflared_<version>_<arch>.deb` in the pool of Cloudflare's repository after `get_url` checked its SHA-256 against `cloudflared_deb_sha256`; the download directory is removed afterwards. A newer installed version is replaced. | `cloudflared --version`; no package file left |
| apt pin | `/etc/apt/preferences.d/cloudflared` pins the version with priority 1001; the signed repository is an apt source (`/etc/apt/sources.list.d/cloudflared.list`, key `/usr/share/keyrings/cloudflare-main.gpg`) | `apt-cache policy` shows the pinned version as installed and as candidate while the index offers a newer one; the `apt` module in check mode would not upgrade it |
| No self-updates | `--no-autoupdate`; the self-update service and timer of `cloudflared service install` are stopped and removed | `prepare.yml` installs and starts them; after the converge they are gone |
| Token only in a file | `/etc/cloudflared/token`, mode 0600, owner `cloudflared`, in `/etc/cloudflared` (`root:cloudflared`, 0750); the unit passes `--token-file`; the task that writes it has `no_log` and no diff, and the variable is `no_log` in the argument spec | owner, mode and content; `systemctl cat`, `systemctl show`, the process command line and the journal contain no token; the journal shows the tunnel ID of the test token, so the service user read and parsed the file |
| Takeover of `cloudflared service install` | the role's unit replaces `/etc/systemd/system/cloudflared.service`, the file that installer writes (releases before 2026.7.2 put the token on its command line) | `prepare.yml` writes such a unit; afterwards neither its token nor `--token` appears |
| Own service user | system user and group `cloudflared`, home `/nonexistent`, shell `/usr/sbin/nologin` | `getent passwd` |
| Sandbox | `NoNewPrivileges`, no capabilities, `ProtectSystem=strict`, `ProtectHome`, private `/tmp` and `/dev`, kernel, clock, host name and control group protection, `ProtectProc=invisible`, `MemoryDenyWriteExecute`, `RestrictNamespaces`, address families `AF_INET AF_INET6 AF_UNIX AF_NETLINK`, system call filter `@system-service` without `@privileged @resources` | unit content, `systemd-analyze verify`; `systemd-analyze security` rates the unit file 1.3 ("OK", 0 is best, 10 worst) and the scenario fails above 1.5; the service runs in it as `cloudflared` without a restart |
| Metrics on one address | `--metrics 127.0.0.1:2000` (`cloudflared_metrics_address`); the role refuses `0.0.0.0` and `[::]` | the only TCP listener of the service is `127.0.0.1:2000`; `/metrics` answers with the version, `/ready` with 503 and no connections |
| Start waits for the tunnel | `Type=notify`: systemd waits up to 30 seconds for the first connection to the edge, so a wrong token or a blocked port fails the start or restart; `Restart=on-failure` | not checked: Molecule has no tunnel (see [Testing](#testing)) |

## Variables

The table is generated from [`meta/argument_specs.yml`](meta/argument_specs.yml), which Ansible
also uses to check the variables when the role starts.

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

## Tags

`cloudflared` (every task) and one tag per part: `cloudflared_package`, `cloudflared_token`,
`cloudflared_service`. The checks at the start always run.

## Metrics and health

The listener at `cloudflared_metrics_address` serves `/metrics` (Prometheus format, for example
`cloudflared_tunnel_ha_connections`) and `/ready`, which answers 200 when the connector has at
least one connection to the edge and 503 otherwise:

```bash
curl -s http://127.0.0.1:2000/ready
```

## Upgrading cloudflared

Dependabot cannot see the version, so it is bumped by hand:

1. Pick a release on <https://github.com/cloudflare/cloudflared/releases> and read its entry in
   `RELEASE_NOTES`. Skip releases marked "Do not use" (2026.8.0 and 2026.8.1 are).
2. Copy the SHA-256 values of `cloudflared-linux-amd64.deb` and `cloudflared-linux-arm64.deb`
   from the release's checksum list. These are the files in the repository's pool (checked for
   2026.10.2 on 2026-10-21).
3. Set `cloudflared_version` and `cloudflared_deb_sha256` in the inventory and run the play on
   one host first. The role updates the pin, downloads and checks the new file, installs it and
   restarts the connector, which waits until the tunnel is connected again.

To go back, set the previous version and its checksums; the role installs older versions too.
The restart interrupts the tunnel for a few seconds unless a second connector of the same tunnel
runs on another host.

## Testing

`molecule/default` converges the role on Debian 13 and Ubuntu 24.04 (systemd containers), runs
it a second time and expects `changed=0`, then checks the controls in the table above.
`prepare.yml` sets up what `cloudflared service install` leaves on a host (a unit with a token
on its command line and the self-update timer), so the converge has to take it over. The
connector then really starts, with a synthetic token that belongs to no account, under a
Molecule-only drop-in: `PrivateNetwork=yes` gives it a network namespace with only a loopback
interface, and `Type=simple` replaces `Type=notify`, because without a connection cloudflared
never reports readiness. `converge.yml` adds `--edge 127.0.0.1:7844` through
`cloudflared_extra_args`, so cloudflared keeps retrying a loopback address instead of looking up
Cloudflare's edge and exiting. The only traffic to Cloudflare is the download of the package
file, the key and the apt index from `pkg.cloudflare.com`.

```bash
cd roles/cloudflared && export MOLECULE_ROLE=cloudflared && molecule test
```

## Limitations

- No real tunnel has been connected: there is no tunnel token for tests, and the scenario must
  not reach Cloudflare. Still to be checked on a virtual machine with a tunnel: the dashboard
  shows the connector as healthy with four connections, `/ready` answers 200, a public hostname
  of the tunnel answers, the `Type=notify` start waits for the connection (and fails within 30
  seconds with a wrong token), and `ss -tlnp` shows no listener except `127.0.0.1:2000`.
- Only x86_64 is tested. The arm64 checksum was compared with the file in the repository's pool,
  but that file was not installed.
- Cloudflare's repository index lists only the newest version, so the role downloads the
  pinned version from the pool. If Cloudflare stops serving old files there, the install of a
  host fails until the version is bumped ([ADR 0011](../../docs/adr/0011-pinned-cloudflared-package-file-with-checksum.md)).
- When Cloudflare replaces its signing key, `apt-get update` reports an error for this source
  until the role runs again and fetches the new key. `cloudflared_apt_repository_enabled: false`
  installs without the apt source.
- cloudflared still reads a `config.yml` from `/etc/cloudflared` or `/usr/local/etc/cloudflared`
  if one exists, for example from an earlier locally managed tunnel; options on the command line
  win over it. The role does not remove such a file.
- Only the tunnel connector is in scope: public hostnames, Access policies and the tunnel itself
  are configured in Cloudflare. Routing private networks through the tunnel (WARP) is not tested.
