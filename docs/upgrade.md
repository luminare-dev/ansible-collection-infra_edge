# Upgrading

Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0.0 a minor
release may contain breaking changes; they are listed under "BREAKING CHANGES" in the
[changelog](../CHANGELOG.md). After 1.0.0, breaking changes come only in a major release.

## General steps

1. Read the changelog entries between your version and the new one.
2. Back up what the roles change on your hosts (configuration, data).
3. Install the new release (see [Installation](install.md)) and verify its checksum. With a
   `requirements.yml`, change the `version:` tag and run
   `ansible-galaxy collection install -r requirements.yml --force`.
4. Run your playbook with `--check --diff` against one host first, then for real, and run the
   check from [Installation](install.md) again.

## Version notes

A release that needs manual steps gets a section here, named after its version.
