#!/usr/bin/env python3
"""Audit all four *built* ESP-Hosted modules; never count source-only checks as ABI PASS."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

TRANSPORTS = ("sdio", "spi", "usb", "spi_hd")
MACHINES = {
    "x86": ("Advanced Micro Devices X86-64", "Intel 80386"),
    "arm": ("ARM",),
    "arm64": ("AArch64",),
}
# Kernel modules must not reference compiler runtime division helpers.
FORBIDDEN_ARM = ("__aeabi_uldivmod", "__aeabi_ldivmod", "__udivdi3", "__divdi3")


def command(argv):
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=20, check=False)
    if result.returncode:
        raise ValueError(f"{argv[0]} failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout


def audit_one(folder, transport, version, arch):
    errors = []
    module = folder / transport / f"esp32_{transport}.ko"
    modinfo = folder / transport / "modinfo.txt"
    check = folder / transport / "sha256.txt"
    if not module.is_file() or module.stat().st_size == 0:
        return ["module missing or empty: " + str(module)]
    if not modinfo.is_file() or not modinfo.read_text().strip():
        errors.append("modinfo evidence missing")
    if not check.is_file():
        errors.append("sha256 evidence missing")
    else:
        digest = check.read_text().strip().split()
        actual = hashlib.sha256(module.read_bytes()).hexdigest()
        if not digest or not re.fullmatch(r"[0-9a-fA-F]{64}", digest[0]) or digest[0].lower() != actual:
            errors.append("SHA-256 mismatch")
    try:
        elf = command(["readelf", "-h", str(module)])
        m = re.search(r"^\s*Machine:\s*(.*?)\s*$", elf, re.M)
        machine = m.group(1) if m else "UNKNOWN"
        if not any(v in machine for v in MACHINES[arch]):
            errors.append(f"module ELF machine {machine!r} does not match {arch}")
        magic = command(["modinfo", "-F", "vermagic", str(module)]).strip()
        if not (magic == version or magic.startswith(version + " ")):
            errors.append(f"module vermagic mismatch {magic!r} != {version}")
        if arch == "arm":
            symbols = command(["readelf", "-Ws", str(module)])
            for symbol in FORBIDDEN_ARM:
                if re.search(r"\bUND\b[^\n]*\b" + re.escape(symbol) + r"\b", symbols):
                    errors.append("forbidden compiler runtime undefined symbol " + symbol)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        errors.append(str(exc))
    return errors


def audit(folder, version, arch):
    result = {}
    for transport in TRANSPORTS:
        errors = audit_one(folder, transport, version, arch)
        result[transport] = {"status": "PASS" if not errors else "FAIL", "errors": errors}
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--directory", required=True, type=Path)
    p.add_argument("--kernel", required=True)
    p.add_argument("--arch", required=True, choices=sorted(MACHINES))
    a = p.parse_args()
    report = {"kernel": a.kernel, "arch": a.arch,
              "scope": "ELF/vermagic/hash/linkage, not runtime transport or hardware",
              "transports": audit(a.directory, a.kernel, a.arch)}
    failures = sum(v["status"] == "FAIL" for v in report["transports"].values())
    report["status"] = "FAIL" if failures else "PASS"
    a.directory.mkdir(parents=True, exist_ok=True)
    (a.directory / "module-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    suite = ET.Element("testsuite", name=f"kernel-module-abi-{a.kernel}-{a.arch}",
                       tests=str(len(TRANSPORTS)), failures=str(failures))
    for name, info in report["transports"].items():
        case = ET.SubElement(suite, "testcase", name=name, classname="kernel.module_abi")
        if info["errors"]:
            ET.SubElement(case, "failure", message="; ".join(info["errors"]))
    ET.ElementTree(suite).write(a.directory / "module-audit-junit.xml",
                                encoding="utf-8", xml_declaration=True)
    print(json.dumps(report, indent=2))
    return int(failures != 0)


if __name__ == "__main__":
    sys.exit(main())
