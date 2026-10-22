"""Source-extraction regression for the production SDIO RX counter helper."""
from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".gitlab/ci/software/run_sdio_logic.py"
spec = importlib.util.spec_from_file_location("run_sdio_logic", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SDIOExtractionTests(unittest.TestCase):
    def test_exact_production_function_is_extracted(self):
        source = (ROOT / "host/sdio/esp_sdio.c").read_text()
        body = module.extract_u32_function(source, "esp_sdio_rx_len_delta")
        self.assertIn("ESP_RX_BYTE_MAX", body)
        self.assertIn("rx_byte_count", body)
        self.assertIn("raw_len", body)

    def test_forward_declaration_is_ignored(self):
        text = """static u32 esp_sdio_rx_len_delta(u32 a, u32 b);
static u32 esp_sdio_rx_len_delta(u32 a, u32 b)
{
    return a - b;
}
"""
        body = module.extract_u32_function(text, "esp_sdio_rx_len_delta")
        self.assertIn("return a - b;", body)

    def test_duplicate_definition_is_rejected(self):
        text = """static u32 esp_sdio_rx_len_delta(u32 a, u32 b) { return a; }
static u32 esp_sdio_rx_len_delta(u32 a, u32 b) { return b; }
"""
        with self.assertRaises(ValueError):
            module.extract_u32_function(text, "esp_sdio_rx_len_delta")


if __name__ == "__main__":
    unittest.main()
