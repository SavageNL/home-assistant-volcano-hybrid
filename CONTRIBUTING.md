# Contribution guidelines

Contributing to this project should be as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features

## Github is used for everything

Github is used to host code, to track issues and feature requests, as well as accept pull requests.

Pull requests are the best way to propose changes to the codebase.

1. Fork the repo and create your branch from `main`.
2. If you've changed something, update the documentation.
3. Make sure your code lints (using `scripts/lint`).
4. Test you contribution.
5. Issue that pull request!

## Any contributions you make will be under the MIT Software License

In short, when you submit code changes, your submissions are understood to be under the same [MIT License](http://choosealicense.com/licenses/mit/) that covers the project. Feel free to contact the maintainers if that's a concern.

## Report bugs using Github's [issues](../../issues)

GitHub issues are used to track public bugs.
Report a bug by [opening a new issue](../../issues/new/choose); it's that easy!

## Write bug reports with detail, background, and sample code

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can.
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening, or stuff you tried that didn't work)

People *love* thorough bug reports. I'm not even kidding.

## Use a Consistent Coding Style

Use [black](https://github.com/ambv/black) to make sure the code follows the style.

## Test your code modification

This custom component is based on [integration_blueprint template](https://github.com/ludeeus/integration_blueprint).

It comes with development environment in a container, easy to launch
if you use Visual Studio Code. With this container you will have a stand alone
Home Assistant instance running and already configured with the included
[`configuration.yaml`](./config/configuration.yaml)
file.

## Releasing

Releases are **tag-driven** — pushing a git tag is the only step. There is no
manual version bump to commit; the version lives in the tag.

1. Make sure `main` is green (lint + tests) and contains everything you want to
   ship.
2. Pick the next [semver](https://semver.org/) version and create a tag for it
   (lightweight is fine), then push the tag:

   ```bash
   git tag 1.0.4
   git push origin 1.0.4
   ```

3. Pushing the tag triggers [`.github/workflows/release.yml`](.github/workflows/release.yml),
   which:
   - checks out the tagged commit,
   - derives the version from the tag name (a leading `v` is stripped, so both
     `1.0.4` and `v1.0.4` work),
   - stamps that version into `manifest.json` **in CI only** (never committed),
   - zips `custom_components/volcano_hybrid/` into `volcano_hybrid.zip`, and
   - publishes a GitHub release with that zip attached, using whatever has
     accumulated under `## [Unreleased]` in [`CHANGELOG.md`](CHANGELOG.md) as
     the release notes, followed by GitHub's auto-generated commit list.

### The changelog

Add an entry under `## [Unreleased]` in [`CHANGELOG.md`](CHANGELOG.md) in the
same pull request as any user-facing change. There is no version to set: that
block *is* the release notes for whatever gets tagged next, so releasing stays
a single tag push.

After a release you can rename the block to the version you just shipped and
open an empty `## [Unreleased]` above it, to keep a per-version history in the
file. That is bookkeeping for readers of the changelog only — nothing in the
release process depends on it.

If `## [Unreleased]` is empty the release still publishes, with auto-generated
notes only, and logs a warning in the workflow run. It warns rather than fails
because the tag already points at that commit, so a missing entry cannot be
fixed by editing the changelog afterwards.

HACS installs from the zip asset (`zip_release`/`filename` in
[`hacs.json`](hacs.json)), so the `version` committed in `manifest.json` is only
a placeholder that the build overwrites — you don't need to touch it.

### Pre-releases

A tag whose version contains `-alpha`, `-beta`, or `-rc` is published as a GitHub
**pre-release**, which HACS only offers to users who have enabled showing beta
versions. Use these to get a testable build out without promoting it to everyone:

```bash
git tag 1.0.4-rc1
git push origin 1.0.4-rc1
```

### Notes

- Git refuses to create a tag that already exists, so a version can't be reused
  by accident.
- To rebuild a release for a tag that already exists, run the **Publish Release**
  workflow manually (Actions → Publish Release → Run workflow) and pass the tag
  name.

## License

By contributing, you agree that your contributions will be licensed under its MIT License.
