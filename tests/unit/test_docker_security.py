import os
import shutil
import subprocess
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

    assert {"gzip", "libpcre2-8-0", "libsqlite3-0", "perl-base", "zlib1g"} <= set(only_upgrade_packages)


def test_distroless_upgrades_zlib_before_staging_runtime_libraries() -> None:
    dockerfile = (_REPO_ROOT / "Dockerfile.distroless").read_text(encoding="utf-8")
    build = dockerfile.split(" AS python-build", maxsplit=1)[1].split("\nFROM ", maxsplit=1)[0]
    only_upgrade_packages = (
        build.split("--only-upgrade \\\n", maxsplit=1)[1].split("&&", maxsplit=1)[0].replace("\\", "").split()
    )

    assert "zlib1g" in only_upgrade_packages
    assert build.index("--only-upgrade") < build.index('cp -a "/lib/${ARCH}-linux-gnu"')
    assert build.index("--only-upgrade") < build.index('cp -a "/usr/lib/${ARCH}-linux-gnu"')
    runtime = dockerfile.rsplit(" AS runtime", maxsplit=1)[1]
    assert "COPY --from=python-build /staged-libs/lib/ /lib/" in runtime
    assert "COPY --from=python-build /staged-libs/usr/lib/ /usr/lib/" in runtime


@pytest.mark.skipif(shutil.which("dpkg") is None, reason="requires Debian version comparison")
@pytest.mark.parametrize(
    ("installed_version", "succeeds"),
    [
        ("1:1.3.dfsg+really1.3.1-1+b1", False),
        ("1:1.3.dfsg+really1.3.1-1+b2", False),
        ("1:1.3.dfsg+really1.3.1-1+deb13u1", True),
        ("1:1.3.dfsg+really1.3.1-1+deb13u1+b1", True),
        ("1:1.3.dfsg+really1.3.1-1+deb13u2", True),
        ("", False),
    ],
    ids=["vulnerable-base", "vulnerable-rebuild", "fixed", "fixed-rebuild", "newer-security", "missing"],
)
def test_runtime_zlib_build_assertion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, installed_version: str, succeeds: bool
) -> None:
    dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile.rsplit(" AS runtime", maxsplit=1)[1]
    apt_run = runtime.split("RUN apt-get update", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]
    assertion = next(
        command.replace("\\\n", "").strip() for command in apt_run.split("&&") if "dpkg --compare-versions" in command
    )

    query = tmp_path / "dpkg-query"
    query.write_text(
        "#!/bin/sh\ntest \"$*\" = '-W -f=${Version} zlib1g' || exit 1\nprintf '%s' \"$TEST_ZLIB_VERSION\"\n",
        encoding="utf-8",
    )
    query.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)
    monkeypatch.setenv("TEST_ZLIB_VERSION", installed_version)

    result = subprocess.run(["sh", "-ec", assertion], capture_output=True, text=True, timeout=5)

    assert (result.returncode == 0) is succeeds, result.stderr
