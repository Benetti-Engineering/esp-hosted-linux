"""Actual production SPI classification function extraction contracts."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".gitlab/ci/software"))
from run_usb_parser import extract_function


class SpiParserExtractionTests(unittest.TestCase):
    def test_real_spi_parser_and_stateful_paths_extracted(self):
        source = (ROOT / "host/spi/esp_spi.c").read_text()
        functions = {x: extract_function(source, x) for x in
                     ("spi_get_cmd_info", "spi_is_stateful_packet", "spi_is_dummy_rx")}
        self.assertIn("PACKET_TYPE_COMMAND_REQUEST", functions["spi_get_cmd_info"])
        self.assertIn("ESP_HCI_IF", functions["spi_is_stateful_packet"])
        self.assertIn("ESP_RCP_IF", functions["spi_is_stateful_packet"])
        self.assertIn("header->if_type == 0xF", functions["spi_is_dummy_rx"])
        self.assertIn("spi_is_dummy_rx(", source)
        self.assertIn("spi_get_cmd_info(", source)

    def test_missing_source_path_fails_extraction(self):
        with self.assertRaises(ValueError):
            extract_function("static bool spi_foo(void) { return true; }",
                             "spi_is_dummy_rx")


if __name__ == "__main__":
    unittest.main()
