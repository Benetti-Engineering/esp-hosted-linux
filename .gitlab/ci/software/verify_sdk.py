#!/usr/bin/env python3
"""Strict offline SDK preflight. Does not build or deploy any image."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ARM64_PAGES = {
    4096: "CONFIG_ARM64_4K_PAGES=y",
    16384: "CONFIG_ARM64_16K_PAGES=y",
    65536: "CONFIG_ARM64_64K_PAGES=y",
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sdk",type=Path,required=True)
    ap.add_argument("--arch",choices=["x86","arm","arm64"],required=True)
    ap.add_argument("--kernel",required=True)
    ap.add_argument("--page-size",type=int,choices=[4096,16384,65536],required=True)
    ap.add_argument("--cc",default=None,help="Compiler executable/tuple matching the SDK")
    args=ap.parse_args()
    sdk=args.sdk.resolve()
    errors=[]
    for name in ("Makefile",".config","Module.symvers"):
        if not (sdk / name).is_file() or (sdk / name).stat().st_size==0:
            errors.append(f"missing/nonempty required: {name}")
    cfg=(sdk / ".config").read_text() if (sdk / ".config").is_file() else ""
    for sym in ("CONFIG_MODULES","CONFIG_MMC","CONFIG_SPI","CONFIG_USB","CONFIG_CFG80211","CONFIG_BT"):
        if not re.search(r"^"+sym+r"=[ym]$",cfg,re.M):
            errors.append(f"missing enabled symbol: {sym}")
    if args.arch=="arm64":
        sym=ARM64_PAGES[args.page_size]
        if sym not in cfg.splitlines():
            errors.append(f"wrong ARM64 page size; require {sym}")
    elif args.page_size != 4096:
        errors.append("non-4K page size requires arm64 in this initial matrix")
    # A kernel source directory and .config do not establish the compiled
    # architecture. Require the actual ELF kernel from the same prepared SDK.
    vmlinux = sdk / "vmlinux"
    if not vmlinux.is_file() or vmlinux.stat().st_size == 0:
        errors.append("SDK lacks built vmlinux; architecture unverified")
    else:
        try:
            elf = subprocess.run(["readelf", "-h", str(vmlinux)], text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=20, check=False)
            m = re.search(r"^\s*Machine:\s*(.*?)\s*$", elf.stdout, re.M)
            machine = m.group(1) if m else "UNKNOWN"
            expected = {"x86": ("X86-64", "80386"),
                        "arm": ("ARM",),
                        "arm64": ("AArch64",)}[args.arch]
            if elf.returncode != 0 or not any(machine == e or e in machine for e in expected):
                errors.append(f"vmlinux ELF architecture mismatch: {machine}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append("ELF architecture probe failed: " + str(exc))
    if not errors:
        try:
            r=subprocess.run(["make","-s","-C",str(sdk),"kernelversion"],text=True,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,check=False)
            if r.returncode!=0 or r.stdout.strip()!=args.kernel:
                errors.append(f"kernelversion mismatch: {r.stdout.strip()} (rc={r.returncode})")
        except (OSError,subprocess.TimeoutExpired) as exc:
            errors.append("kernelversion probe failed: "+str(exc))
    if args.cc:
        try:
            r=subprocess.run([args.cc,"-dumpmachine"],text=True,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=False)
            triple=r.stdout.strip()
            expected={"x86":("x86_64","i686"),"arm":("arm","gnueabihf"),
                      "arm64":("aarch64",)}[args.arch]
            if r.returncode != 0 or not any(s in triple for s in expected):
                errors.append(f"compiler/arch mismatch: {triple} (rc={r.returncode})")
        except (OSError,subprocess.TimeoutExpired) as exc:
            errors.append("compiler probe failed: "+str(exc))
    def digest(name):
        path = sdk / name
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    report={"sdk":str(sdk),"arch":args.arch,"kernel":args.kernel,
            "config_sha256":digest(".config"), "symvers_sha256":digest("Module.symvers"),
            "page_size":args.page_size,"errors":errors,"status":"PASS" if not errors else "FAIL"}
    print(json.dumps(report,indent=2))
    return bool(errors)

if __name__=="__main__":
    sys.exit(main())
