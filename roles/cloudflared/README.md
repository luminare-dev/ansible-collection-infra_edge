# luminare.infra_edge.cloudflared

Connector for a remotely managed Cloudflare Tunnel on a Debian 13 or Ubuntu 24.04 host: a pinned
cloudflared version installed from its package file after a SHA-256 check and held with an apt
pin, the tunnel token in a file only the service user can read, and a sandboxed systemd service.
The host needs no open inbound port; the connector only connects out to Cloudflare on port 7844.

## Requirements

- Debian 13 or Ubuntu 24.04 on x86_64 or aarch64 (only x86_64 is tested), reached as root or with
  `become: true`.
- Outbound HTTPS to `pkg.cloudflare.com` and outbound port 7844 (UDP and TCP).
- A remotely managed tunnel and its token (from the install command in the Cloudflare dashboard,
  or `GET /accounts/<account_id>/cfd_tunnel/<tunnel_id>/token`). Public hostnames are configured
  in Cloudflare, not on the host.

## Example playbook

```yaml
- name: Run the tunnel connector
  hosts: edge
  become: true
  roles:
    - role: luminare.infra_edge.cloudflared
```

By default the token is read from `TUNNEL_TOKEN` on the control node:

```bash
read -rs TUNNEL_TOKEN && export TUNNEL_TOKEN
ansible-playbook -i inventory.yml edge.yml
```

Or set `cloudflared_token: "{{ vault_cloudflared_token }}"` from Ansible Vault or SOPS.

## What it sets up

- `cloudflared_version` (2026.10.2) from the pool of Cloudflare's repository, checked against
  `cloudflared_deb_sha256` and pinned in `/etc/apt/preferences.d/cloudflared`; `--no-autoupdate`.
- `/etc/cloudflared/token` (0600, owner `cloudflared`), passed with `--token-file`; it never
  appears on a command line, in the unit or in Ansible output.
- A sandboxed unit running as the system user `cloudflared`, with `Type=notify` (the start waits
  up to 30 seconds for the first connection).
- Metrics on `127.0.0.1:2000` only: `/metrics` and `/ready` (200 when connected).
- Takes over a connector set up with `cloudflared service install` and removes its self-update
  units.

## Variables

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

`cloudflared`, `cloudflared_package`, `cloudflared_token`, `cloudflared_service`. The input
checks always run.

## Upgrading cloudflared

Dependabot cannot see the version, so it is bumped by hand:

1. Pick a release on <https://github.com/cloudflare/cloudflared/releases> and skip any marked
   "Do not use".
2. Copy the SHA-256 values of `cloudflared-linux-amd64.deb` and `cloudflared-linux-arm64.deb`
   from the release's checksum list.
3. Set `cloudflared_version` and `cloudflared_deb_sha256` and run the play on one host first.

Going back works the same way with the old version and checksums. The restart interrupts the
tunnel for a few seconds unless a second connector runs on another host.

## Testing

```bash
cd roles/cloudflared && export MOLECULE_ROLE=cloudflared && molecule test
```

The scenario starts the connector with a synthetic token in a network namespace without access
to Cloudflare.

## Limitations

- Not tested with a real tunnel yet.
- Cloudflare's apt index only lists the newest version, so the role downloads the pinned one from
  the pool. If Cloudflare removes old files there, installs fail until the version is bumped.
- A `config.yml` in `/etc/cloudflared` from an earlier locally managed tunnel is still read
  (command-line options win); the role does not remove it.
