# Roles

Each role of the collection lives in its own folder here and is used by its fully qualified name,
`luminare.infra_edge.<role>`. A role folder holds:

- `defaults/main.yml`: every variable, prefixed with the role name;
- `meta/argument_specs.yml`: type, default and description of every variable, checked when the
  role starts;
- `README.md`: what the role does and its variable table;
- `molecule/default/`: the role's Molecule scenario (`molecule.yml`, `converge.yml`,
  `verify.yml`). The driver, the two test platforms and the test sequence come from the shared
  [`.config/molecule/config.yml`](../.config/molecule/config.yml); CI finds every
  `roles/*/molecule/default/molecule.yml` and runs it in one job per platform (Debian 13,
  Ubuntu 24.04). Every role needs this scenario: a unit test fails for a role folder without it.
