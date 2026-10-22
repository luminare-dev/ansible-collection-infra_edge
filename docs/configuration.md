# Configuration

Each role of the collection is configured through its own variables. Every variable starts with
the role name (for example `<role>_enabled`), has its default in `roles/<role>/defaults/main.yml`
and is described, with its type, in `roles/<role>/meta/argument_specs.yml`, which Ansible checks
when the role starts. Each role gets a section on this page with a table of its options (option,
type, default, description), written from that file.

This version of the collection contains no role yet, so there is nothing to configure.

## Secrets

Secrets never go into this repository, an issue or a log. A role takes a secret only as a
variable (from Ansible Vault, a SOPS-encrypted vars file or an environment lookup in your own
inventory), never as a default value, and every task that handles a secret sets `no_log: true`.
CI scans every commit with gitleaks; a leaked secret is rotated first and removed from history
second.
