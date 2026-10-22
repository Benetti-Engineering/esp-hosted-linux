/* Userspace shim for the actual two production esp_usb.c parser functions.
 * The generator injects those C functions at the two marked positions;
 * there is NO copied parser implementation in this harness.
 * This does not exercise USB URB lifecycle, I/O, or the hardware controller.
 */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "adapter.h"
#include "esp_host_wire_bounds.h"
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error This native USB parser harness requires little-endian host
#endif
typedef uint8_t u8;
typedef uint16_t u16;
#define ESP_USB_MAX_XFER (16 * 1024)
#define esp_wire_le16_to_cpu(v) (v)

struct esp_usb_context {
    u8 rx_stream[ESP_USB_MAX_XFER * 2];
    size_t rx_stream_len;
    u16 bulk_in_mps;
    bool rx_pad_expected;
    unsigned frames;
    u8 ids[32];
    size_t lengths[32];
    bool fail_next_queue;
};

/* GENERATED_VALID_HEADER */

static bool esp_usb_queue_frame_locked(struct esp_usb_context *ctx,
                                        const u8 *data, size_t len)
{
    const struct esp_payload_header *h = (const struct esp_payload_header *)data;
    if (ctx->fail_next_queue) {
        ctx->fail_next_queue = false;
        return false;
    }
    assert(ctx->frames < 32);
    ctx->ids[ctx->frames] = h->reserved1;
    ctx->lengths[ctx->frames] = len;
    ctx->frames++;
    return true;
}

/* GENERATED_PARSE_STREAM */

static bool append_and_parse(struct esp_usb_context *ctx, const u8 *data,
                             size_t count, bool *loss)
{
    assert(ctx->rx_stream_len + count <= sizeof(ctx->rx_stream));
    memcpy(ctx->rx_stream + ctx->rx_stream_len, data, count);
    ctx->rx_stream_len += count;
    return esp_usb_parse_stream_locked(ctx, loss);
}

static size_t frame(u8 *dst, size_t payload, u8 id, u8 iface)
{
    struct esp_payload_header h = {0};
    assert(payload && sizeof(h) + payload <= ESP_USB_MAX_XFER);
    h.if_type = iface;
    h.offset = (u16)sizeof(h);
    h.len = (u16)payload;
    h.reserved1 = id;
    memcpy(dst, &h, sizeof(h));
    memset(dst + sizeof(h), id + 1, payload);
    return sizeof(h) + payload;
}

static void test_fragmentation_and_coalescing(void)
{
    struct esp_usb_context ctx = {0};
    u8 bytes[128];
    size_t a = frame(bytes, 11, 5, ESP_STA_IF);
    size_t b = frame(bytes + a, 17, 6, ESP_AP_IF);
    bool loss = false;
    assert(!append_and_parse(&ctx, bytes, 3, &loss));
    assert(ctx.frames == 0 && ctx.rx_stream_len == 3);
    assert(append_and_parse(&ctx, bytes + 3, a + b - 3, &loss));
    assert(ctx.frames == 2 && ctx.ids[0] == 5 && ctx.ids[1] == 6);
    assert(ctx.lengths[0] == a && ctx.lengths[1] == b);
    assert(ctx.rx_stream_len == 0 && !loss);
}

static void test_short_urb_slices(void)
{
    struct esp_usb_context ctx = {0};
    u8 bytes[256];
    size_t size = 0;
    bool loss = false;
    for (unsigned id = 0; id < 5; id++)
        size += frame(bytes + size, 7 + id, (u8)id, ESP_STA_IF);
    for (size_t p = 0; p < size;) {
        size_t n = (p % 5) + 1;
        if (n > size - p)
            n = size - p;
        append_and_parse(&ctx, bytes + p, n, &loss);
        p += n;
    }
    assert(ctx.frames == 5 && ctx.rx_stream_len == 0 && !loss);
    for (unsigned id = 0; id < 5; id++)
        assert(ctx.ids[id] == id);
}

static void test_invalid_prefix_resync(void)
{
    struct esp_usb_context ctx = {0};
    u8 bytes[128];
    memset(bytes, 0xff, 7);
    size_t len = frame(bytes + 7, 11, 9, ESP_STA_IF);
    bool loss = false;
    assert(append_and_parse(&ctx, bytes, 7 + len, &loss));
    assert(loss && ctx.frames == 1 && ctx.ids[0] == 9);
}

static void test_padding_exact_mps(void)
{
    struct esp_usb_context ctx = {0};
    u8 bytes[160];
    ctx.bulk_in_mps = 64;
    size_t first = frame(bytes, 52, 10, ESP_STA_IF); /* exactly 64 */
    assert(first == 64);
    bytes[first] = 0; /* real firmware's short logical frame pad */
    size_t second = frame(bytes + first + 1, 9, 11, ESP_STA_IF);
    bool loss = false;
    assert(append_and_parse(&ctx, bytes, first + 1 + second, &loss));
    assert(ctx.frames == 2 && ctx.ids[0] == 10 && ctx.ids[1] == 11);
    assert(ctx.rx_stream_len == 0 && !ctx.rx_pad_expected && !loss);
}

static void test_queue_failure_requests_loss(void)
{
    struct esp_usb_context ctx = {0};
    u8 bytes[64];
    bool loss = false;
    size_t n = frame(bytes, 19, 7, ESP_STA_IF);
    ctx.fail_next_queue = true;
    assert(!append_and_parse(&ctx, bytes, n, &loss));
    assert(loss && ctx.frames == 0 && ctx.rx_stream_len == 0);
}

static void test_truncated_body_waits(void)
{
    struct esp_usb_context ctx = {0};
    u8 bytes[64];
    bool loss = false;
    size_t n = frame(bytes, 35, 4, ESP_STA_IF);
    assert(!append_and_parse(&ctx, bytes, sizeof(struct esp_payload_header), &loss));
    assert(ctx.frames == 0 && !loss);
    assert(append_and_parse(&ctx, bytes + sizeof(struct esp_payload_header),
                            n - sizeof(struct esp_payload_header), &loss));
    assert(ctx.frames == 1 && ctx.rx_stream_len == 0 && !loss);
}

static void test_invalid_header_bounds(void)
{
    struct esp_usb_context ctx = {0};
    u8 bytes[64];
    size_t n = frame(bytes, 9, 12, ESP_STA_IF);
    struct esp_payload_header *h = (struct esp_payload_header *)bytes;
    size_t len = 0;
    h->offset = 0;
    assert(!esp_usb_valid_header(&ctx, h, &len));
    h->offset = 17;
    assert(!esp_usb_valid_header(&ctx, h, &len));
    h->offset = 12;
    h->len = 0;
    assert(!esp_usb_valid_header(&ctx, h, &len));
    h->len = ESP_USB_MAX_XFER;
    assert(!esp_usb_valid_header(&ctx, h, &len));
    h->len = 9;
    h->if_type = ESP_MAX_IF;
    assert(!esp_usb_valid_header(&ctx, h, &len));
    h->if_type = ESP_STA_IF;
    assert(esp_usb_valid_header(&ctx, h, &len) && len == n);
    assert(!esp_usb_valid_header(NULL, h, &len));
    assert(!esp_usb_valid_header(&ctx, NULL, &len));
}

int main(void)
{
    test_fragmentation_and_coalescing();
    test_short_urb_slices();
    test_invalid_prefix_resync();
    test_padding_exact_mps();
    test_queue_failure_requests_loss();
    test_truncated_body_waits();
    test_invalid_header_bounds();
    puts("PASS: production USB stream parser fragment/coalesce/resync/MPS/error");
    return 0;
}
