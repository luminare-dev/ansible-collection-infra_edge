# luminare.infra_edge.nginx

Reverse proxy for a Debian 13 or Ubuntu 24.04 edge host behind an outbound tunnel: nginx from the
distribution with one site per application, each listening on a loopback address for the tunnel
connector on the same host (see [`cloudflared`](../cloudflared/README.md)). The client address
comes from the connector's `CF-Connecting-IP` header, which is trusted only from `127.0.0.1`.
Requests are logged as JSON, the version is hidden, security headers are added, websockets are
passed through, and the optional stream module relays TCP and UDP ports to another host. `nginx -t`
checks the whole configuration before every reload.

## Requirements

- Managed host: Debian 13 or Ubuntu 24.04 with systemd and Python 3, reached as root or with
  `become: true`. The role stops before any change on another distribution.
- The distribution's package mirror: the role installs `nginx` (1.26 on Debian 13, 1.24 on
  Ubuntu 24.04) and, for relays, `libnginx-mod-stream`.
- A tunnel connector on the same host whose public hostnames point to the site listeners, for
  example the service `http://127.0.0.1:8080`. Without one, the sites answer only on the host
  itself.
- For relays on a host with the [`base`](../base/README.md) firewall: the role writes their ports
  into `/etc/nftables.d/20-nginx.nft`.
- Control node: ansible-core 2.20 or later. The role uses only `ansible.builtin` modules.

## Example playbook

```yaml
- name: Serve the applications through the tunnel
  hosts: edge
  become: true
  roles:
    - role: luminare.infra_edge.nginx
      vars:
        nginx_sites:
          - name: status
            server_name: lab-status.example.com
            listen: 127.0.0.1:8080
            upstream: http://127.0.0.1:3001
            websocket: true
          - name: docs
            server_name: lab-docs.example.com
            listen: 127.0.0.1:8081
            upstream: http://127.0.0.1:4000
```

In the tunnel's configuration in Cloudflare, the public hostname `lab-status.example.com` then
gets the service `http://127.0.0.1:8080` and `lab-docs.example.com` the service
`http://127.0.0.1:8081`. Use `127.0.0.1`, not `localhost`: the address must match
`nginx_real_ip_from` (a site on `[::1]` also needs `::1` there).

## What the role does

| Control | How | Checked in Molecule |
|---|---|---|
| Loopback listeners only | each site listens on `127.0.0.1:<port>` or `[::1]:<port>`; the role refuses any other address; the package's default site (port 80 on every address) is removed | `ss`: nginx listens on `127.0.0.1:8080`, `127.0.0.1:8081` and the relay port only, and nothing listens on port 80 |
| Client address from the connector only | `set_real_ip_from 127.0.0.1`, `real_ip_header CF-Connecting-IP`, `real_ip_recursive off` ([ADR 0014](../../docs/adr/0014-client-address-from-the-loopback-connector-only.md)); the application gets the checked address in `X-Real-IP`, `X-Forwarded-For` and `CF-Connecting-IP`, never an address list from the request, and no `Forwarded` header | a request from `127.0.0.1` with `CF-Connecting-IP: 203.0.113.7`, a forged `X-Forwarded-For` and a forged `Forwarded` reaches the application and the log as `203.0.113.7` only; the same header from `127.0.0.2` is ignored |
| Scheme for the application | `X-Forwarded-Proto` from a trusted connector (`https` for a public hostname), from any other client the listener's scheme | `https` from `127.0.0.1`, `http` from `127.0.0.2` |
| JSON access log | `/var/log/nginx/access.log`, one JSON object per request (see [Access log](#access-log)); the query string is not logged; files `0640 www-data:adm`, kept 14 days by the package's logrotate rule | every line parses as JSON; client and connector address, site and upstream of the test requests; the token in a query string is not in the log; owner and mode |
| No version | `server_tokens off` | `Server: nginx` on a proxied answer and on nginx's own 502 page |
| Security headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, added with `always` (error pages too) unless the application sends the header itself; `X-Powered-By` removed; no `Strict-Transport-Security` (TLS ends at the tunnel's edge, which sets it) | present on a 200 and on a 502; the application's own `X-Frame-Options: DENY` stays, once |
| Websockets | `websocket: true` passes `Upgrade` and `Connection` on and allows 1 hour without data (`nginx_websocket_read_timeout`) | the handshake gets `101` and data goes both ways; on a site without it the application sees a plain `GET` |
| Compression | gzip for text, JSON, JavaScript, XML and SVG of at least 256 bytes, proxied answers included, with `Vary: Accept-Encoding` | a proxied JSON answer comes back with `Content-Encoding: gzip` |
| Checked before every reload | after all files are written, `nginx -t` checks the whole configuration on every run; the reload handler runs only after it passed. A failed check stops the play, nginx keeps serving the old configuration, and the next run fails at the same check until the input is fixed ([ADR 0013](../../docs/adr/0013-nginx-conf-owned-by-the-role-and-checked-every-run.md)) | `nginx -t`; `nginx -T` shows the hardening settings |
| Sites follow the inventory | every site file starts with a marker line; a file with the marker whose site is no longer in `nginx_sites` is removed together with its symlink | after `side_effect.yml` drops the `api` site, its file, symlink and listener are gone |
| Relays (optional) | `nginx_stream_enabled` installs the stream module and adds one upstream and one server per relay, TCP and UDP (UDP with `reuseport`), with a JSON log in `/var/log/nginx/stream-access.log` | TCP and UDP data through port 30120 to a test echo service; the stream log entry |
| Firewall for the relays | when `/etc/nftables.d` exists (or with `nginx_firewall_manage: true`, which also creates it): `20-nginx.nft` with `add rule inet filter input … accept` lines for the relay ports from `nginx_firewall_sources`, checked together with `/etc/nftables.conf` by `nft --check` before it replaces the old file; a running nftables is restarted (a running fail2ban after it); the file is removed when no relay is left | converge with `nginx_firewall_manage: true` and no directory: directory, file and content; after the restart the loaded input chain accepts the relay port and keeps `policy drop`; a second run with the default after the relay is turned off: file and rules are gone |

## Variables

The table is generated from [`meta/argument_specs.yml`](meta/argument_specs.yml), which Ansible
also uses to check the variables when the role starts, including the keys of every site and
relay. The role also refuses values with spaces, quotes, semicolons or braces where they would
end up in the nginx configuration.

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

## Tags

`nginx` (every task) and one tag per part: `nginx_install`, `nginx_config`, `nginx_service`,
`nginx_firewall`. The checks at the start always run, and `nginx_config` includes the `nginx -t`
check.

## Access log

Each request is one line of JSON in `/var/log/nginx/access.log`, for example (from the Molecule
scenario, shortened):

```json
{"time":"2026-10-21T16:54:49+00:00","remote_addr":"203.0.113.8","realip_remote_addr":"127.0.0.1","server_name":"demo.example.com","host":"demo.example.com","method":"GET","path":"/molecule-after-removal","protocol":"HTTP/1.1","status":200,"bytes_sent":580,"request_time":0.001,"upstream_addr":"127.0.0.1:9000","upstream_status":"200","upstream_response_time":"0.001","cf_ray":""}
```

`remote_addr` is the client address after the check, `realip_remote_addr` the address of the
connection (the connector). The full object also has `referer` and `user_agent`. The query string
is not logged, because it may carry tokens. The log holds client addresses, which are personal
data: the package's logrotate rule rotates it daily and keeps 14 files. `nginx_json_access_log:
false` switches to nginx's `combined` format.

## Relays

The stream module forwards TCP and UDP ports unchanged, for example to a game server on another
host:

```yaml
nginx_stream_enabled: true
nginx_stream_upstreams:
  - name: game
    listen: 30120
    upstream: 192.0.2.13:30120
    protocols: [tcp, udp]
```

A relay listens on a public address (`listen: 30120` means every IPv4 address), so on a host with
the base firewall the role opens the port for `nginx_firewall_sources` (everyone by default). The
target sees the address of the relay host, not the client's. A UDP session is logged when it ends,
after 10 minutes without data.

## Testing

`molecule/default` converges the role on Debian 13 and Ubuntu 24.04 (systemd containers), runs it
a second time and expects `changed=0`, then checks the controls in the table above. `prepare.yml`
loads a firewall in the base role's layout (input policy drop, include of `/etc/nftables.d`, but
without the directory) into the instance's own network namespace and starts a test application:
HTTP on `127.0.0.1:9000`, which answers with the request headers it received, and TCP and UDP
echo on `127.0.0.1:9001`. `converge.yml` sets up two sites (`demo` with websockets, `api`
without) and a TCP and UDP relay on port 30120, with `nginx_firewall_manage: true`.
`verify.yml` sends its requests with a test client that can also connect from `127.0.0.2`, a
loopback address that is not a trusted proxy. After that, `side_effect.yml` applies the role with
the default firewall setting, without the `api` site and without the relay, and
`verify_removed.yml` checks that both are gone from the configuration, the listeners and the
firewall.

```bash
cd roles/nginx && export MOLECULE_ROLE=nginx && molecule test
```

## Limitations

- The sites speak plain HTTP on loopback addresses: TLS ends at the tunnel's edge, and the hop from
  the connector to nginx stays on the host. An `upstream` on another host is plain HTTP too, so
  keep it on a private network; HTTPS to upstreams with an internal certificate authority is not
  part of this version.
- Every process on the host that connects from `127.0.0.1` is trusted like the connector, so a
  local user can set any client address. Other hosts cannot reach the listeners.
- No real tunnel has been connected: in Molecule the test client sends the connector's headers.
  Still to be checked with a tunnel: the log shows the visitors' addresses and `https`.
- The firewall restart was tested in the network namespace of a container. That a relay port is
  reachable from another host and other ports are not is still to be checked on a virtual
  machine.
- The role owns `/etc/nginx/nginx.conf` and overwrites local changes; extra `http` settings go
  into `/etc/nginx/conf.d/*.conf`. When a package update ships a changed `nginx.conf`, dpkg asks
  which file to keep: a manual `apt upgrade` shows the question (keep the installed one), and
  unattended-upgrades holds that update back and logs it until someone installs it by hand.
- When nginx refuses a reload although `nginx -t` passed (for example, another process already
  holds a new port), the reload handler still succeeds: nginx keeps the old configuration and
  writes the reason to `/var/log/nginx/error.log`.
- Between the package installation and the first reload, the package's default site listens on
  port 80 of every address for a few seconds; the base firewall drops that port.
- Only x86_64 is tested.
