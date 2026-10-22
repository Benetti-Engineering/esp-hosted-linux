"""Executable negative tests for kernel .ko artifact audit. No kernel boot claim."""
import importlib.util
from pathlib import Path
import hashlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".gitlab/ci/software/audit_modules.py"
spec = importlib.util.spec_from_file_location("module_audit", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class AuditModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for t in mod.TRANSPORTS:
            folder = self.root / t
            folder.mkdir()
            raw = b"\x7fELF" + t.encode()
            (folder / f"esp32_{t}.ko").write_bytes(raw)
            (folder / "modinfo.txt").write_text("license: GPL\n")
            (folder / "sha256.txt").write_text(hashlib.sha256(raw).hexdigest() + "  module\n")

    def fake_command(self, args):
        if args[:2] == ["readelf", "-h"]:
            return "  Machine:                           ARM\n"
        if args[:2] == ["readelf", "-Ws"]:
            return "Num: Value Size Type Bind Vis Ndx Name\n"
        if args[:3] == ["modinfo", "-F", "vermagic"]:
            return "6.1.184 SMP mod_unload ARMv7 p2v8\n"
        raise AssertionError(args)

    def test_all_four_proper_artifact_sets_pass(self):
        with patch.object(mod, "command", self.fake_command):
            results = mod.audit(self.root, "6.1.184", "arm")
        self.assertEqual(list(results), list(mod.TRANSPORTS))
        self.assertTrue(all(x["status"] == "PASS" for x in results.values()))

    def test_missing_module_fails_only_its_backend(self):
        (self.root / "usb" / "esp32_usb.ko").unlink()
        with patch.object(mod, "command", self.fake_command):
            results = mod.audit(self.root, "6.1.184", "arm")
        self.assertEqual(results["usb"]["status"], "FAIL")
        self.assertTrue(all(results[t]["status"] == "PASS" for t in mod.TRANSPORTS if t != "usb"))

    def test_corrupt_hash_is_rejected(self):
        (self.root / "spi" / "esp32_spi.ko").write_bytes(b"\x7fELFchanged")
        with patch.object(mod, "command", self.fake_command):
            errors = mod.audit_one(self.root, "spi", "6.1.184", "arm")
        self.assertIn("SHA-256 mismatch", errors)

    def test_wrong_machine_and_vermagic_fail_closed(self):
        def invalid(args):
            if args[:2] == ["readelf", "-h"]:
                return "Machine: AArch64\n"
            if args[0] == "modinfo":
                return "4.9.337 SMP\n"
            return ""
        with patch.object(mod, "command", invalid):
            errors = mod.audit_one(self.root, "sdio", "6.1.184", "arm")
        self.assertTrue(any("machine" in e for e in errors))
        self.assertTrue(any("vermagic" in e for e in errors))

    def test_32bit_arm_undefined_compiler_division_is_rejected(self):
        def division(args):
            if args[:2] == ["readelf", "-Ws"]:
                return "   12: 00000000 0 NOTYPE GLOBAL DEFAULT UND __aeabi_uldivmod\n"
            return self.fake_command(args)
        with patch.object(mod, "command", division):
            errors = mod.audit_one(self.root, "spi_hd", "6.1.184", "arm")
        self.assertTrue(any("__aeabi_uldivmod" in e for e in errors))

    def test_native_x86_does_not_receive_arm_undefined_symbol_policy(self):
        def x86(args):
            if args[:2] == ["readelf", "-h"]:
                return "  Machine: Advanced Micro Devices X86-64\n"
            if args[0] == "modinfo":
                return "6.12.105 SMP\n"
            return self.fake_command(args)
        with patch.object(mod, "command", x86):
            self.assertEqual(mod.audit_one(self.root, "spi_hd", "6.12.105", "x86"), [])

    def test_cli_nonzero_and_machine_readelf_errors(self):
        # The directory is intentionally not an ELF: real readelf must reject
        # it, and CLI must fail instead of granting module ABI credit.
        r = subprocess.run(["python3", str(SCRIPT), "--directory", str(self.root),
                            "--kernel", "6.1.184", "--arch", "arm"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue((self.root / "module-audit.json").is_file())
        self.assertTrue((self.root / "module-audit-junit.xml").is_file())


if __name__ == "__main__":
    unittest.main()
