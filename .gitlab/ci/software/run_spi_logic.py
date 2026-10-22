#!/usr/bin/env python3
"""Compile actual production SPI no-I/O classification functions with C sanitizer."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
from run_usb_parser import extract_function

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "host/spi/esp_spi.c"
HARNESS = ROOT / "tests/software/spi_parser_harness.c"
FUNCTIONS = ("spi_get_cmd_info", "spi_is_stateful_packet", "spi_is_dummy_rx")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    src = SOURCE.read_text()
    harness = HARNESS.read_text()
    marker = "/* GENERATED_SPI_FUNCTIONS */"
    if harness.count(marker) != 1:
        raise ValueError("SPI harness marker changed")
    harness = harness.replace(marker, "\n\n".join(extract_function(src, n)
                                                   for n in FUNCTIONS))
    generated = out / "spi-production-parser.c"
    generated.write_text(harness)
    exe = out / "spi-production-parser"
    sanitizer = os.environ.get("SOFTWARE_SANITIZERS", "undefined")
    if sanitizer not in ("undefined", "address,undefined", "none"):
        raise ValueError("unsupported sanitizer")
    cmd = shlex.split(os.environ.get("CC", "gcc")) + [
        "-std=c11", "-g", "-O1", "-Wall", "-Wextra", "-Werror",
        "-fno-omit-frame-pointer", "-I", str(ROOT / "host/include"),
        str(generated), "-o", str(exe)]
    if sanitizer != "none":
        cmd += ["-fsanitize=" + sanitizer]
    for stage, argv in (("compile", cmd), ("execute", [str(exe)])):
        run = subprocess.run(argv, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=90, check=False)
        print(stage.upper() + ": " + " ".join(argv))
        print(run.stdout)
        if run.returncode:
            return run.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
