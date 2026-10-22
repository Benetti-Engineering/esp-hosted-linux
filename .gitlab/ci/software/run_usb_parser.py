#!/usr/bin/env python3
"""Extract and exercise production USB stream parsing with a minimal userspace shim.

Only the two parser functions are extracted from host/usb/esp_usb.c.
Kernel URB/disconnect/recovery scheduling is NOT executed or qualified.
"""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "host/usb/esp_usb.c"
HARNESS = ROOT / "tests/software/usb_stream_parser_harness.c"


def extract_typed_function(text, name, return_type):
    """Extract one static C function definition with the requested return type."""
    import re

    pattern = re.compile(r"(?m)^[ \\t]*static[ \\t]+"
                         + re.escape(return_type) + r"[ \\t]+"
                         + re.escape(name) + r"[ \\t]*\(")
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
            raise ValueError("unterminated function signature: " + name)
        brace = end_args
        while brace < len(text) and text[brace].isspace():
            brace += 1
        if brace < len(text) and text[brace] == ";":
            continue
        if brace >= len(text) or text[brace] != "{":
            raise ValueError("unexpected function body for: " + name)
        depth = 0
        for index in range(brace, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    definitions.append(text[match.start():index + 1])
                    break
        else:
            raise ValueError("unterminated production function: " + name)
    if len(definitions) != 1:
        raise ValueError("missing or ambiguous production function: " + name)
    return definitions[0]


def extract_function(text, name):
    """Backward-compatible bool-function extractor used by parser harnesses."""
    return extract_typed_function(text, name, "bool")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = SOURCE.read_text()
    harness = HARNESS.read_text()
    for name, marker in (
        ("esp_usb_valid_header", "/* GENERATED_VALID_HEADER */"),
        ("esp_usb_parse_stream_locked", "/* GENERATED_PARSE_STREAM */"),
    ):
        if harness.count(marker) != 1:
            raise ValueError("missing/ambiguous harness marker: " + marker)
        harness = harness.replace(marker, extract_function(source, name))
    generated = out / "usb-production-parser.c"
    generated.write_text(harness)
    binary = out / "usb-production-parser"
    sanitizer = os.environ.get("SOFTWARE_SANITIZERS", "undefined")
    if sanitizer not in ("undefined", "address,undefined", "none"):
        raise ValueError("unsupported SOFTWARE_SANITIZERS")
    cc = shlex.split(os.environ.get("CC", "gcc"))
    cmd = cc + ["-std=c11", "-g", "-O1", "-Wall", "-Wextra", "-Werror",
                "-fno-omit-frame-pointer", "-I", str(ROOT / "host/include"),
                str(generated), "-o", str(binary)]
    if sanitizer != "none":
        cmd += ["-fsanitize=" + sanitizer]
    for stage, argv, timeout in (("compile", cmd, 90), ("execute", [str(binary)], 90)):
        result = subprocess.run(argv, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout, check=False)
        print(stage.upper() + ": " + " ".join(argv))
        print(result.stdout)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
