"""Extract and execute the production SDIO RX producer-counter wrap helper.

This qualifies only pure counter arithmetic. MMC host locking, CMD52/53,
DMA mapping, IRQ and remove/recovery races remain NOT_EXECUTED.
"""
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "host/sdio/esp_sdio.c"
HARNESS = ROOT / "tests/software/sdio_rx_counter_harness.c"


def extract_u32_function(text, name):
    pattern = re.compile(r"(?m)^[ \t]*static[ \t]+u32[ \t]+"
                         + re.escape(name) + r"[ \t]*\(")
    definitions = []
    for match in pattern.finditer(text):
        depth = 0
        end_args = None
        for index in range(match.end() - 1, len(text)):
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
                if depth == 0:
                    end_args = index + 1
                    break
        if end_args is None:
            raise ValueError("unterminated SDIO function signature")
        brace = end_args
        while brace < len(text) and text[brace].isspace():
            brace += 1
        if brace < len(text) and text[brace] == ";":
            continue
        if brace >= len(text) or text[brace] != "{":
            raise ValueError("unexpected SDIO function body")
        depth = 0
        for index in range(brace, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    definitions.append(text[match.start():index + 1])
                    break
    if len(definitions) != 1:
        raise ValueError("missing or ambiguous production SDIO function")
    return definitions[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    harness = HARNESS.read_text()
    marker = "/* GENERATED_SDIO_RX_LEN_DELTA */"
    if harness.count(marker) != 1:
        raise ValueError("SDIO harness marker changed")
    source = SOURCE.read_text()
    harness = harness.replace(marker, extract_u32_function(
        source, "esp_sdio_rx_len_delta"))

    generated = out / "sdio-production-rx-counter.c"
    generated.write_text(harness)
    exe = out / "sdio-production-rx-counter"

    sanitizer = os.environ.get("SOFTWARE_SANITIZERS", "undefined")
    if sanitizer not in ("undefined", "address,undefined", "none"):
        raise ValueError("unsupported SOFTWARE_SANITIZERS")
    cmd = shlex.split(os.environ.get("CC", "gcc")) + [
        "-std=c11", "-g", "-O1", "-Wall", "-Wextra", "-Werror",
        "-fno-omit-frame-pointer", str(generated), "-o", str(exe)]
    if sanitizer != "none":
        cmd += ["-fsanitize=" + sanitizer]

    for stage, argv in (("compile", cmd), ("execute", [str(exe)])):
        result = subprocess.run(argv, cwd=ROOT, text=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                timeout=90, check=False)
        print(stage.upper() + ": " + " ".join(argv))
        print(result.stdout)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
