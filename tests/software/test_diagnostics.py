"""Mutation fixtures check the actual production warning analyzer."""
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/".gitlab/ci/software/check_diagnostics.py"

class DiagnosticTests(unittest.TestCase):
    def run_fixture(self,text):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"warnings.log"
            p.write_text(text)
            result=subprocess.run([sys.executable,str(SCRIPT),"--log",str(p),
                                   "--label","fixture"],capture_output=True,text=True)
            return result.returncode
    def test_gcc_warning_is_rejected(self):
        self.assertEqual(self.run_fixture(
            "/build/repo/host/spi/esp_spi.c:77:9: warning: unsafe code\n"),1)
    def test_clang_warning_is_rejected(self):
        self.assertEqual(self.run_fixture(
            "host/usb/esp_usb.c:22:15: warning: unused variable [-Wunused-variable]\n"),1)
    def test_sparse_warning_is_rejected(self):
        self.assertEqual(self.run_fixture(
            "host/sdio/esp_sdio.c:19:7: sparse: incorrect type in assignment\n"),1)
    def test_missing_include_is_rejected(self):
        self.assertEqual(self.run_fixture(
            "cc1: warning: missing include directory [-Wmissing-include-dirs]\n"),1)
    def test_unrelated_kernel_warning_is_not_host_debt(self):
        self.assertEqual(self.run_fixture(
            "/usr/src/linux/mm/filemap.c:22: warning: unrelated upstream warning\n"),0)
    def test_missing_log_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"missing.log"
            proc=subprocess.run([sys.executable,str(SCRIPT),"--log",str(p),
                                 "--label","fixture"],capture_output=True)
            self.assertEqual(proc.returncode,2)
