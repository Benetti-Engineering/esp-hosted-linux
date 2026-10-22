"""Extraction is source-backed and fails closed when USB production parser drifts."""
from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".gitlab/ci/software/run_usb_parser.py"
spec = importlib.util.spec_from_file_location("run_usb_parser", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class UsbParserExtractionTests(unittest.TestCase):
    def test_extracts_actual_two_kernel_functions(self):
        data = (ROOT / "host/usb/esp_usb.c").read_text()
        for fn in ("esp_usb_valid_header", "esp_usb_parse_stream_locked"):
            extracted = module.extract_function(data, fn)
            self.assertTrue(extracted.startswith("static bool " + fn + "("))
            self.assertTrue(extracted.strip().endswith("}"))
        parser = module.extract_function(data, "esp_usb_parse_stream_locked")
        self.assertIn("esp_usb_queue_frame_locked", parser)
        self.assertIn("rx_pad_expected", parser)
        self.assertIn("memmove", parser)
        self.assertIn("stream_loss", parser)

    def test_forward_declaration_is_ignored(self):
        source = ("static bool spi_get_cmd_info(int value);\n"
                  "static bool spi_get_cmd_info(int value)\n"
                  "{\n    return value > 0;\n}\n")
        actual = module.extract_function(source, "spi_get_cmd_info")
        self.assertEqual(actual.count("static bool spi_get_cmd_info"), 1)
        self.assertIn("return value > 0", actual)
        self.assertNotIn(");", actual)

    def test_two_definitions_fail_closed(self):
        source = ("static bool example(void) { return true; }\n"
                  "static bool example(void) { return false; }\n")
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            module.extract_function(source, "example")

    def test_missing_function_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            module.extract_function("static int unrelated(void) { return 0; }",
                                    "esp_usb_parse_stream_locked")

    def test_corrupt_unclosed_function_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unterminated"):
            module.extract_function("static bool esp_usb_valid_header(void) {", "esp_usb_valid_header")

    def test_kernel_path_invokes_parser(self):
        data = (ROOT / "host/usb/esp_usb.c").read_text()
        self.assertIn("esp_usb_parse_stream_locked(ctx, &stream_loss)", data)
        self.assertIn("esp_usb_ingest_stream(", data)


if __name__ == "__main__":
    unittest.main()
