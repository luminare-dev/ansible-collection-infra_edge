# 0014. Client address from the loopback connector only instead of X-Forwarded-For or Cloudflare's address ranges

- **Status:** accepted
- **Date:** 2026-10-21

## Context

Behind the tunnel, every request reaches nginx from the connector (`cloudflared`) on the same
host, so the address of the connection is always `127.0.0.1`. The visitor's address arrives in
the `CF-Connecting-IP` header and in `X-Forwarded-For`, to which Cloudflare appends the address
after any list that the visitor sent. Logs, rate limits and applications need the visitor's
address, and nobody else may be able to choose it. Applications also need the public scheme
(`X-Forwarded-Proto`) to build their links.

## Considered options

1. Trust `CF-Connecting-IP` only from `127.0.0.1` (`set_real_ip_from`, `real_ip_header`,
   `real_ip_recursive off`), and pass the checked address to the application as `X-Real-IP`,
   `X-Forwarded-For` and `CF-Connecting-IP`; drop a `Forwarded` header (RFC 7239) from the
   request. Pass `X-Forwarded-Proto` on only from the same addresses.
2. Trust `X-Forwarded-For` recursively from Cloudflare's published address ranges.
3. Pass the headers to the application unchanged (`$proxy_add_x_forwarded_for`).

## Decision

Option 1, with the listeners on loopback addresses only, so that the connector on the host is
the only remote client. Option 2 is meant for an origin that Cloudflare's proxies connect to
directly; with the tunnel they never do, and the ranges change over time. Option 3 hands a list
that the visitor can choose to the application, and an application that reads its first entry
can be given any address.

## Consequences

- Good: the Molecule scenario shows that a forged `X-Forwarded-For` is replaced by the checked
  address and a forged `Forwarded` does not reach the application, and that the same `CF-Connecting-IP` from `127.0.0.2` is ignored for the log, for the
  application and for `X-Forwarded-Proto`.
- Bad: every process on the host that connects from `127.0.0.1` is trusted like the connector,
  so local users can set any address.
- Bad: a connector on another host is not supported: it would need a non-loopback listener, which
  the role refuses in this version, and its address in `nginx_real_ip_from`.
