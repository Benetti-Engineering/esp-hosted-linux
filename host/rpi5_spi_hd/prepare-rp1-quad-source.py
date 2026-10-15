#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage DesignWare sources without modifying the cached kernel checkout."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

FILES = ("spi-dw-core.c", "spi-dw-dma.c", "spi-dw-mmio.c", "spi-dw.h", "internals.h")
QUAD_REF = "81a76dd2284e09547cc5a9eeb88b174fea5a819a"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def main():
    cache = Path(os.environ.get("CACHE_DIR", str(Path.home() / ".cache/esp-hosted-rpi5-spi-hd"))).resolve()
    repo = cache / "linux"
    if not (repo / ".git").is_dir():
        raise RuntimeError(f"Kernel cache missing: {repo}; run build-rp1-quad-modules.sh first")
    base = os.environ.get("SPI_DW_BASE_REF", "HEAD")
    # Capture the exact kernel source used; a cached checkout's HEAD is
    # potentially mutable even though the upstream quad PR SHA is pinned.
    base_sha = git(repo, "rev-parse", "--verify", base + "^{commit}").decode().strip()
    print(f"QSPI_KERNEL_BASE_SHA={base_sha}", file=__import__("sys").stderr)
    print(f"QSPI_QUAD_PR_SHA={QUAD_REF}", file=__import__("sys").stderr)
    git(repo, "rev-parse", "--verify", QUAD_REF + "^{commit}")
    parent = git(repo, "rev-parse", QUAD_REF + "^").decode().strip()
    upstream_patch = git(repo, "diff", parent, QUAD_REF, "--",
                         "drivers/spi/spi-dw-core.c", "drivers/spi/spi-dw-dma.c", "drivers/spi/spi-dw.h")
    local_patch = Path(__file__).with_name("kernel-patches") / "0001-spi-dw-quad-dma.patch"
    print(f"QSPI_LOCAL_PATCH_SHA256={hashlib.sha256(local_patch.read_bytes()).hexdigest()}",
          file=__import__("sys").stderr)
    stage = Path(tempfile.mkdtemp(prefix=".qspi-source-", dir=cache))
    try:
        spi = stage / "drivers/spi"
        spi.mkdir(parents=True)
        for name in FILES:
            (spi / name).write_bytes(git(repo, "show", f"{base_sha}:drivers/spi/{name}"))
        for patch in (upstream_patch, local_patch.read_bytes()):
            subprocess.run(["patch", "-d", str(stage), "-p1", "--batch", "--forward", "--fuzz=0"],
                           input=patch, check=True)
        digest = hashlib.sha256()
        for name in FILES:
            digest.update(name.encode())
            digest.update((spi / name).read_bytes())
        final = cache / ("qspi-source-" + digest.hexdigest()[:16])
        if final.exists():
            for name in FILES:
                if (final / "drivers/spi" / name).read_bytes() != (spi / name).read_bytes():
                    raise RuntimeError(f"Existing source cache differs: {final}")
        else:
            stage.rename(final)
        print(final)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == "__main__":
    main()
