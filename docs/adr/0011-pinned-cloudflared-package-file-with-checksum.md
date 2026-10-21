# 0011. Pinned cloudflared package file with a checksum instead of the newest package from the repository

- **Status:** accepted
- **Date:** 2026-10-21

## Context

The `cloudflared` role must install a known cloudflared version, the same on every host and in
every test run, and change it only through a reviewed change. Cloudflare publishes cloudflared
in a signed apt repository (`https://pkg.cloudflare.com/cloudflared`, suite `any`) and as GitHub
releases with a SHA-256 list. On 2026-10-21 the repository index listed only one version,
2026.10.3 (released that day), while its pool still served the package files of older versions
(2026.10.2, 2026.9.1, 2025.1.0 and others were checked). So `apt-get install cloudflared=<version>`
works only until the next release, and there were four in October 2026 alone. The pool files
of 2026.10.2 for amd64 and arm64 have the same SHA-256 as `cloudflared-linux-amd64.deb` and
`cloudflared-linux-arm64.deb` of the GitHub release. cloudflared also updates itself when it
is installed with `cloudflared service install` (a daily timer).

## Considered options

1. Install the package file of the pinned version from the repository's pool, check its SHA-256
   against a value in the role, keep the signed repository as an apt source and hold the version
   with an apt pin (priority 1001).
2. Add the repository and install `cloudflared=<version>` with apt, as the plan described.
3. Add the repository and install the newest version on every run.
4. Download the static binary from the GitHub release.

## Decision

Option 1, with version 2026.10.2 instead of the 2026.9.1 that the plan named: 2026.10.0 fixed
request path normalization with Access rules (VULN-141859), 2026.10.1 updated Go for
GO-2026-6600, and 2026.10.2 fixed dropped message tails (TUN-10994). 2026.10.3 changes no
behaviour (build image, Go version directive, lint fixes) and was a few hours old; its
`cloudflared-linux-amd64` binary is built with the same Go 1.27.3 as that of 2026.10.2 (checked
on 2026-10-22), so it brings no security fix either and 2026.10.2 stays pinned.

The role writes the pin file first, adds the repository (key fetched on every run, replaced only
when it changed), reads the installed version with `dpkg-query` and, only when it differs,
downloads `cloudflared_<version>_<arch>.deb` into a root-only directory with `get_url` and
`checksum: sha256:…`, installs it (downgrades allowed, so the pin always wins) and deletes the
directory. It removes the installer's self-update units and starts cloudflared with
`--no-autoupdate`.

Option 2 breaks on the next upstream release, also in the weekly CI run. Option 3 is not
reproducible and moves every host at Cloudflare's pace. Option 4 bypasses the package manager, so
`dpkg -S` and the apt pin would not cover the binary.

## Consequences

- Good: every host and every Molecule run gets the same file, checked against a SHA-256 that is
  reviewed in the pull request that changes the version; a newer version from the repository
  never replaces it (the Molecule scenario checks this with `apt-cache policy` and with the `apt`
  module in check mode while the index offers a newer version).
- Good: a host on which cloud-init installed a newer version from the repository is moved to the
  pinned version.
- Bad: Dependabot cannot update the version; it is bumped by hand together with both checksums
  (role README, "Upgrading cloudflared").
- Bad: if Cloudflare ever stops serving old files from the pool, installing the pinned version
  fails until the version is bumped.
- Bad: the apt source points to Cloudflare's repository, so a key change on Cloudflare's side
  makes `apt-get update` report an error for that source until the role runs again; set
  `cloudflared_apt_repository_enabled: false` to install without the apt source.
