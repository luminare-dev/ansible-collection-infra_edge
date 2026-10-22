# 0009. One nftables ruleset with a drop-in directory instead of a firewall per role

- **Status:** accepted
- **Date:** 2026-10-21

## Context

Several roles open ports on the same host: a web server, a database for a few application
hosts, application ports, metrics exporters. Each role should only open its own port, nothing
may be open by default, and roles from other collections must be able to add rules without
knowing the others. Debian and Ubuntu both ship `nftables.service`, which loads
`/etc/nftables.conf`.

## Considered options

1. `base` owns `/etc/nftables.conf` with policy drop; other roles add files to
   `/etc/nftables.d/`, included by the last line.
2. Each role creates its own nftables table and chains.
3. ufw with one rule per role.

## Decision

Option 1. `/etc/nftables.conf` starts with `flush ruleset`, defines `table inet filter` with the
chains `input` (policy drop; loopback, established and related connections, ICMP and ICMPv6,
DHCPv6 replies to the client port 546 from link-local addresses, and SSH per `base_ssh_allow_mode`
accepted), `forward` (policy drop) and `output` (policy accept), and
its last line is `include "/etc/nftables.d/*.nft"`. A role adds `/etc/nftables.d/<NN>-<role>.nft`
with `add rule inet filter input … accept` lines only (20 web server, 30 database, 40 to 49
application ports, 50 metrics exporters), writes it only when `/etc/nftables.d` exists or it is
told to, checks the whole ruleset with `nft -c -f /etc/nftables.conf` and restarts nftables.
Because the input policy is drop, a drop-in never needs a drop rule. `base` removes ufw so that
only one tool manages the rules.

Option 2 spreads the default policy over several tables, where a drop in one table is not
undone by an accept in another, so the result depends on every role. Option 3 hides the
ruleset behind another tool and has no include mechanism for files of other roles.

## Consequences

- Good: one file shows the default policy, `nft -c` checks it together with every drop-in, and
  removing a role's file and restarting nftables closes its port again.
- Good: the Molecule scenario of `base` checks the ruleset without a drop-in, with a valid one
  and with a broken one (which must fail the check).
- Bad: `flush ruleset` also removes rules that other software (for example Docker) adds, so such
  hosts keep `base_firewall_enabled: false`.
- Bad: containers cannot prove that the loaded ruleset blocks traffic; that check needs a
  virtual machine (listed in the README limitations).
