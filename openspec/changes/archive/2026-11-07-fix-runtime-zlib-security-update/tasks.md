## 1. Image security updates

- [x] 1.1 Upgrade runtime zlib1g and assert the Debian 13 fixed-version floor; verify tests reject vulnerable/missing versions and accept fixed/newer versions.
- [x] 1.2 Upgrade distroless zlib1g in the library-source stage; verify package selection and staging/copy order in container security tests.
- [x] 1.3 Check CI, release, and rolling-image workflow inputs and preserve Trivy enforcement; verify existing workflow/packaging tests.

## 2. Validation and documentation

- [x] 2.1 Run `make lint`, `uv run --extra oracle ty check`, affected tests, strict change validation, and canonical spec validation; record results and unavailable Docker/Trivy verification.
- [x] 2.2 Sync the requirement and stable context to github-automation, verify implementation against the artifacts, and archive with a verification report.
