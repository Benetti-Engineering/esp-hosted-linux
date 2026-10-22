#!/usr/bin/env python3
"""Reject driver-source warnings even when GCC/Clang/sparse use different formats."""
import argparse
import pathlib
import re
import sys

# Match diagnostics attributed to the repository's host sources. Kernel headers
# outside host/ are not automatically actionable driver warning debt.
SOURCE = re.compile(r"(?:^|\s)(?:[^\s:]+/)?host/[^\s:]+\.[ch]:\d+(?::\d+)?")
DIAG = re.compile(r"(?:warning:|error:|sparse:)")
MISSING_INCLUDE = re.compile(r"\[-Wmissing-include-dirs\]")

def host_diagnostic(line):
    return bool(MISSING_INCLUDE.search(line) or
                (SOURCE.search(line) and DIAG.search(line)))

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--log",type=pathlib.Path,required=True)
    a.add_argument("--label",required=True)
    args=a.parse_args()
    if not args.log.is_file():
        print("FAIL: diagnostics log missing",file=sys.stderr)
        return 2
    matches=[f"{n}: {line}" for n,line in enumerate(args.log.read_text(
        encoding="utf-8",errors="replace").splitlines(),1) if host_diagnostic(line)]
    if matches:
        print(f"FAIL: {args.label} diagnostics in driver:\n"+"\n".join(matches),file=sys.stderr)
        return 1
    print(f"PASS: {args.label} host diagnostics (no attributable warnings)")
    return 0
if __name__=="__main__":
    sys.exit(main())
