"""Source policy for SDIO DMA-safe buffers.

This is a compile/source contract only. It does not emulate MMC DMA mapping.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SDIODMABufferContractTests(unittest.TestCase):
    def test_persistent_cmd53_buffers_use_dma_safe_allocator(self):
        source = (ROOT / "host/sdio/esp_sdio.c").read_text()

        self.assertIn("#if defined(CONFIG_ZONE_DMA32)", source)
        self.assertIn("#define ESP_SDIO_DMA_GFP (GFP_KERNEL | GFP_DMA32)", source)
        self.assertIn("#define ESP_SDIO_DMA_GFP (GFP_KERNEL | GFP_DMA)", source)

        expected = {
            "reg_buf": r"context->reg_buf\s*=\s*kmalloc\(sizeof\(u32\),\s*ESP_SDIO_DMA_GFP\)",
            "rx_len_buf": r"context->rx_len_buf\s*=\s*kmalloc\(sizeof\(u32\),\s*ESP_SDIO_DMA_GFP\)",
            "token_buf": r"context->token_buf\s*=\s*kmalloc\(sizeof\(u32\),\s*ESP_SDIO_DMA_GFP\)",
            "tx_aggr_buf": r"context->tx_aggr_buf\s*=\s*kzalloc\(ESP_TX_AGGR_SIZE_MAX,\s*ESP_SDIO_DMA_GFP\)",
        }
        for name, pattern in expected.items():
            with self.subTest(buffer=name):
                self.assertRegex(source, pattern)

        # Allocation is deliberately completed before IRQ registration; ISR
        # register access must never depend on an on-demand DMA allocation.
        alloc = source.index("context->reg_buf = kmalloc")
        claim_irq = source.index("sdio_claim_irq(func, esp_handle_isr)", alloc)
        self.assertLess(alloc, claim_irq)

    def test_dma_buffers_are_freed_together_and_pointers_cleared(self):
        source = (ROOT / "host/sdio/esp_sdio.c").read_text()
        fn = source.split("static void esp_sdio_free_dma_bufs", 1)[1].split(
            "#ifdef ESP_DEBUG_STATS", 1)[0]
        for member in ("reg_buf", "rx_len_buf", "token_buf", "tx_aggr_buf"):
            with self.subTest(buffer=member):
                self.assertIn("kfree(context->" + member + ");", fn)
                self.assertIn("context->" + member + " = NULL;", fn)


if __name__ == "__main__":
    unittest.main()
