from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_upgrades_trivy_fixed_debian_packages() -> None:
    dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile.rsplit(" AS runtime", maxsplit=1)[1]
    only_upgrade_packages = (
        runtime.split("--only-upgrade \\\n", maxsplit=1)[1].split("&&", maxsplit=1)[0].replace("\\", "").split()
    )

    assert {"gzip", "libpcre2-8-0", "libsqlite3-0", "perl-base"} <= set(only_upgrade_packages)
