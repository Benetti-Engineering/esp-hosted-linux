#!/usr/bin/env python3
"""Run only implemented tests. Unavailable tests are NOT_EXECUTED, never PASS."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET

SUITES = ("source_contracts", "shared_wire_abi_native", "sdio_production_rx_counter",
          "usb_production_stream_parser", "spi_hd_production_ack", "spi_production_parser")

BACKEND_SUITES = {"sdio": "sdio_production_rx_counter",
                  "usb": "usb_production_stream_parser",
                  "spi_hd": "spi_hd_production_ack",
                  "spi": "spi_production_parser"}


def backend_results(target, suites):
    name = BACKEND_SUITES.get(target)
    if not name:
        return "NOT_EXECUTED", []
    result = next((s for s in suites if s["id"] == name), None)
    if result is None:
        return "NOT_EXECUTED", []
    return ("PARTIAL_SOFTWARE" if result["status"] == "PASS" else "FAIL"), [name]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--out", type=Path, default=Path("build-artifacts/software"))
    ap.add_argument("--suite", action="append", choices=SUITES, help="Select a test suite; default all")
    args = ap.parse_args()
    root = args.root.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads((root / ".gitlab/ci/software/coverage-plan.json").read_text())
    version = os.environ.get("CI_COMMIT_SHA", "local-unknown")
    suites = []
    tests = ET.Element("testsuite", name="esp-hosted-software-foundation")
    compiler = shlex.split(os.environ.get("CC", "gcc"))
    sanitizer = os.environ.get("SOFTWARE_SANITIZERS", "undefined")
    if sanitizer not in ("undefined", "address,undefined", "none"):
        raise SystemExit("Invalid SOFTWARE_SANITIZERS")
    flags = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-g", "-fno-omit-frame-pointer"]
    if sanitizer != "none":
        flags += ["-fsanitize=" + sanitizer]
    exe = out / "wire-abi"
    commands = {
        "source_contracts": [sys.executable, "-m", "unittest", "discover", "-s", "tests/software", "-p", "test_*.py", "-v"],
        "shared_wire_abi_native": compiler + flags + ["-I", "host/include", "tests/software/wire_abi.c", "-o", str(exe)],
        "sdio_production_rx_counter": [sys.executable, ".gitlab/ci/software/run_sdio_logic.py", "--out", str(out)],
        "usb_production_stream_parser": [sys.executable, ".gitlab/ci/software/run_usb_parser.py", "--out", str(out)],
        "spi_hd_production_ack": [sys.executable, ".gitlab/ci/software/run_spi_hd_logic.py", "--out", str(out)],
        "spi_production_parser": [sys.executable, ".gitlab/ci/software/run_spi_logic.py", "--out", str(out)],
    }
    for name in SUITES:
        if args.suite and name not in args.suite:
            continue
        command = commands[name]
        try:
            result = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=150, check=False)
            output = result.stdout
            code = result.returncode
            if name == "shared_wire_abi_native" and code == 0:
                execution = subprocess.run([str(exe)], cwd=root, text=True,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           timeout=150, check=False)
                code = execution.returncode
                output += "\nRUN:\n" + execution.stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            code = 124 if isinstance(exc, subprocess.TimeoutExpired) else 127
            output = str(exc)
        (out / (name + ".log")).write_text(output)
        if code != 0:
            # On shared GitLab runners, source_contracts failures were
            # previously invisible in the job log: only "FAIL (exit 1)"
            # appeared while the actual unittest traceback was hidden in
            # an artifact. Keep the full log artifact and show a bounded
            # failure excerpt immediately for actionable CI diagnostics.
            lines = output.splitlines()
            shown = lines if len(lines) <= 300 else lines[:25] + [f"... {len(lines) - 275} lines omitted; full artifact retained ..."] + lines[-250:]
            print(f"===== {name}: FAIL exit={code}; last {len(shown)}"
                  f" of {len(lines)} diagnostic lines =====", flush=True)
            print("\n".join(shown), flush=True)
            print(f"===== END FAILURE DIAGNOSTICS {name}; complete output in"
                  f" build-artifacts/software/{name}.log =====", flush=True)
        case = ET.SubElement(tests, "testcase", classname="software", name=name)
        if code != 0:
            failure = ET.SubElement(case, "failure", message=f"exit code {code}")
            failure.text = output[-14000:]
        ET.SubElement(case, "system-out").text = output[-14000:]
        suites.append({"id":name,"status":"PASS" if code == 0 else "FAIL",
                       "exit_code":code,"command":command})
    tests.set("tests",str(len(suites)))
    tests.set("failures",str(sum(s["status"]=="FAIL" for s in suites)))
    ET.ElementTree(tests).write(out / "junit.xml", encoding="utf-8", xml_declaration=True)
    coverage = {
        "source_sha":version,
        "sanitizer":sanitizer,
        "kernel_build_sdk":os.environ.get("KERNEL", "not-used-by-foundation"),
        "executed_in_kernel":False,
        "created_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope":"shared production helpers + extracted SDIO, USB, SPI and SPI-HD logic; no physical bus/runtime state machines",
        "shared_suite_results":[s for s in suites if s["id"] not in BACKEND_SUITES.values()],
        "backend_suite_results":[s for s in suites if s["id"] in BACKEND_SUITES.values()],
        "transports":{
            target:{
                "status":backend_results(target, suites)[0],
                "executed_backend_suites":backend_results(target, suites)[1],
                "backend_tests_not_executed":info["planned"],
                "software_integration_not_executed":plan["software_unimplemented"],
                "hardware_not_executed":plan["physical_unimplemented"]
            } for target,info in plan["transports"].items()
        },
        "images_not_built":[x["id"] for x in plan["future_images"] if x["status"] == "NOT_BUILT"]
    }
    (out / "coverage.json").write_text(json.dumps(coverage, indent=2)+"\n")
    for s in suites:
        print(f"{s['id']}: {s['status']} (exit {s['exit_code']})")
    print("IMPORTANT: only selected production logic executed; non-executed backends never count as PASS")
    return int(any(s["status"]!="PASS" for s in suites))

if __name__ == "__main__":
    sys.exit(main())
