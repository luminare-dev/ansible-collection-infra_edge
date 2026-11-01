# luminare.infra_edge.nginx

nginx from the distribution as the reverse proxy behind an outbound tunnel: one site per
application on a loopback listener, the client address from the connector's `CF-Connecting-IP`
header (trusted only from `127.0.0.1`), a JSON access log, no version in `Server`, security
headers, websockets and optional TCP/UDP relays. `nginx -t` checks the whole configuration
before every reload.

## Requirements

- Debian 13 or Ubuntu 24.04, reached as root or with `become: true`.
- A tunnel connector on the same host (see [`cloudflared`](../cloudflared/README.md)) whose
  public hostnames point to the site listeners, for example `http://127.0.0.1:8080`.

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

In Cloudflare, point the hostnames at `http://127.0.0.1:8080` and `http://127.0.0.1:8081`. Use
`127.0.0.1`, not `localhost`, so the address matches `nginx_real_ip_from`.

## What it sets up

- Sites only on `127.0.0.1` or `[::1]`; the package's default site is removed. Sites removed from
  `nginx_sites` are removed from the host.
- `set_real_ip_from 127.0.0.1`, `real_ip_header CF-Connecting-IP`; the application gets the
  checked address in `X-Real-IP`, `X-Forwarded-For` and `CF-Connecting-IP`.
- `server_tokens off`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` (unless the
  application sets them), gzip for text types.
- A JSON access log in `/var/log/nginx/access.log` without query strings (rotated daily, 14 days).
  `nginx_json_access_log: false` switches to `combined`.
- The role owns `/etc/nginx/nginx.conf`; extra `http` settings go into `/etc/nginx/conf.d/`.

## Variables

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

`nginx`, `nginx_install`, `nginx_config` (includes the `nginx -t` check), `nginx_service`,
`nginx_firewall`. The input checks always run.

## Relays

The stream module forwards TCP and UDP ports unchanged, for example to a game server:

```yaml
nginx_stream_enabled: true
nginx_stream_upstreams:
  - name: game
    listen: 30120
    upstream: 192.0.2.13:30120
    protocols: [tcp, udp]
```

On a host with the [`base`](../base/README.md) firewall the role opens the port for
`nginx_firewall_sources` (everyone by default) in `/etc/nftables.d/20-nginx.nft`. The target sees
the relay host's address, not the client's.

## Testing

```bash
cd roles/nginx && export MOLECULE_ROLE=nginx && molecule test
```

## Limitations

- Sites speak plain HTTP; TLS ends at the tunnel's edge. Keep an `upstream` on another host on a
  private network.
- Every local process connecting from `127.0.0.1` is trusted like the connector.
- When a package update ships a changed `nginx.conf`, dpkg asks which file to keep (keep the
  installed one); unattended-upgrades holds such an update back.
