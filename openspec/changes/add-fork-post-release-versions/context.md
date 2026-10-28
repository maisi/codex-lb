# Context

## Why `.postM` on a beta

The fork follows upstream's beta train and, while upstream is quiet, releases
on top of the last upstream beta it merged. The version has to satisfy four
consumers at once:

| Consumer | Needs | `1.25.0-beta.9.post1` |
|---|---|---|
| `pyproject.toml` / `uv.lock` | PEP 440 | `1.25.0b9.post1` |
| Helm chart, `package.json` | semver 2 | prerelease identifiers `beta`, `9`, `post1` |
| Docker tag | `[A-Za-z0-9_.-]` | `1.25.0-beta.9.post1` |
| Dashboard update check | semver ordering | sorts below a later stable |

Ordering is the same in both schemes:
`beta.9 < beta.9.post1 < beta.9.post2 < beta.10`. So when upstream publishes
`beta.10` it is newer than every fork release on `beta.9`, and the fork can go
back to upstream's numbering without renaming anything.

Rejected spellings:

- `beta.10`, `beta.11`: collide with upstream's next betas.
- `beta.9-1`: semver compares `9-1` as text, which sorts above `10`.
- `beta.9.1`: not a PEP 440 version.
- `+fork.1` local versions: not allowed in Docker tags.

## Why skip PyPI in a fork

`codex-lb` on PyPI is published by upstream through trusted publishing. A fork
cannot publish there. Without the skip, the PyPI job fails, the GitHub release
is never written, and the failed-release job turns the release back into a
draft, even though the Docker image and Helm chart were published.

## Cutting a fork release

1. On an up-to-date `main`:
   `python -m scripts.prepare_beta_release --base-version 1.25.0 --beta-number 9 --post-number 1 --changelog-path /tmp/changes.md`,
   then `uv lock`.
2. Commit as `chore: release v1.25.0-beta.9.post1` on branch
   `release/beta-1.25.0-beta.9.post1` and open a PR against `main` with the
   release-candidate validation checklist and the head SHA (same body as the
   automated beta PR).
3. After CI passes, check the evidence items and merge. `Publish Beta Release`
   tags the merge commit and creates the prerelease, which runs `Release`:
   Docker `ghcr.io/<owner>/codex-lb:1.25.0-beta.9.post1` and `:beta`, the Helm
   chart and the GitHub release assets.

The next fork release on the same upstream beta uses `--post-number 2`. Once
upstream publishes a newer beta and it is merged, the fork's files follow
upstream's version again.

Publishing requires the `RELEASE_PLEASE_TOKEN` secret in the fork: a release
created with `GITHUB_TOKEN` does not trigger the `Release` workflow.
