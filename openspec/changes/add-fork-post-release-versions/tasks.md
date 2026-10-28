# Tasks

- [x] `scripts/release_versions.py`: parse `X.Y.Z-beta.N.postM` versions and
      `v…` tags, PEP 440 spelling `X.Y.ZbN.postM`, `uv.lock` canonicalization,
      latest-beta ordering by serial then post number.
- [x] `scripts/prepare_beta_release.py`: `--post-number` (requires
      `--beta-number`).
- [x] `scripts/guard_beta_release.py`: canonicalize a PEP 440 post version in
      `uv.lock` so canonical post-release PRs pass the guard.
- [x] `release.yml`: skip PyPI in forks, create the GitHub release when PyPI was
      skipped, omit the PyPI install line in forks, use the publishing owner in
      the Helm install line.
- [x] Strip `git log`'s record newline so the beta changelog keeps one line per
      commit.
- [x] Unit tests for parsing, ordering, preparation, release metadata, the
      PR / publish guards on a post-release branch, the release workflow's
      fork gates, the dashboard update check and the changelog lines.
- [x] Strict OpenSpec validation.
