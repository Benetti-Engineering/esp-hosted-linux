/* Production esp_sdio_rx_len_delta() is inserted below.
 * No MMC, CMD53, DMA or interrupt behavior is simulated here.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

typedef uint32_t u32;
#define ESP_RX_BYTE_MAX 0x100000U

/* GENERATED_SDIO_RX_LEN_DELTA */

static u32 reference_delta(u32 raw, u32 consumed)
{
    return (raw + ESP_RX_BYTE_MAX - consumed) % ESP_RX_BYTE_MAX;
}

static u32 next_random(u32 *state)
{
    u32 x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

int main(void)
{
    static const u32 points[] = {
        0, 1, 2, 511, 512, 513, 15871, 15872, 15873,
        ESP_RX_BYTE_MAX / 2,
        ESP_RX_BYTE_MAX - 513,
        ESP_RX_BYTE_MAX - 512,
        ESP_RX_BYTE_MAX - 2,
        ESP_RX_BYTE_MAX - 1
    };
    u32 state = 0x31415926U;
    unsigned i, j;

    for (i = 0; i < sizeof(points) / sizeof(points[0]); ++i)
        for (j = 0; j < sizeof(points) / sizeof(points[0]); ++j)
            assert(esp_sdio_rx_len_delta(points[i], points[j]) ==
                   reference_delta(points[i], points[j]));

    assert(esp_sdio_rx_len_delta(0, ESP_RX_BYTE_MAX - 1) == 1);
    assert(esp_sdio_rx_len_delta(8, ESP_RX_BYTE_MAX - 16) == 24);
    assert(esp_sdio_rx_len_delta(15872, 0) == 15872);
    assert(esp_sdio_rx_len_delta(12345, 12345) == 0);

    for (i = 0; i < 200000; ++i) {
        u32 raw = next_random(&state) & (ESP_RX_BYTE_MAX - 1);
        u32 consumed = next_random(&state) & (ESP_RX_BYTE_MAX - 1);
        assert(esp_sdio_rx_len_delta(raw, consumed) ==
               reference_delta(raw, consumed));
    }

    puts("PASS: production SDIO RX producer-counter wrap arithmetic");
    return 0;
}
