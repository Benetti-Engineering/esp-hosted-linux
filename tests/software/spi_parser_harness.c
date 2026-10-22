/* Actual ESP-Hosted standard SPI command/stateful/dummy functions inserted
 * from host/spi/esp_spi.c. No I/O, GPIO, controller or DMA simulation here.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "adapter.h"
typedef uint8_t u8;
typedef uint16_t u16;
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error This native SPI parser harness requires little-endian host
#endif
#define esp_wire_le16_to_cpu(v) (v)

struct sk_buff {
    u8 *data;
    size_t len;
};

/* GENERATED_SPI_FUNCTIONS */

static void test_command_parser(void)
{
    u8 data[128] = {0};
    struct esp_payload_header *h = (struct esp_payload_header *)data;
    struct command_header *cmd = (struct command_header *)(data + sizeof(*h));
    struct sk_buff skb = {.data = data, .len = sizeof(*h) + sizeof(*cmd)};
    u8 opcode = 0;
    u16 seq = 0;
    h->packet_type = PACKET_TYPE_COMMAND_REQUEST;
    h->offset = sizeof(*h);
    cmd->cmd_code = CMD_SCAN_REQUEST;
    cmd->seq_num = 0x1234;
    assert(spi_get_cmd_info(&skb, &opcode, &seq));
    assert(opcode == CMD_SCAN_REQUEST && seq == 0x1234);
    assert(spi_get_cmd_info(&skb, NULL, NULL));
    skb.len = sizeof(*h) - 1;
    assert(!spi_get_cmd_info(&skb, &opcode, &seq));
    skb.len = sizeof(*h) + sizeof(*cmd) - 1;
    assert(!spi_get_cmd_info(&skb, &opcode, &seq));
    skb.len = sizeof(*h) + sizeof(*cmd);
    h->packet_type = PACKET_TYPE_DATA;
    assert(!spi_get_cmd_info(&skb, &opcode, &seq));
    h->packet_type = PACKET_TYPE_COMMAND_REQUEST;
    h->offset = 65535;
    assert(!spi_get_cmd_info(&skb, &opcode, &seq));
    assert(!spi_get_cmd_info(NULL, &opcode, &seq));
}

static void test_stateful_classifier(void)
{
    u8 data[32] = {0};
    struct esp_payload_header *h = (struct esp_payload_header *)data;
    struct sk_buff skb = {.data = data, .len = sizeof(*h)};
    h->if_type = ESP_HCI_IF;
    assert(spi_is_stateful_packet(&skb));
    h->if_type = ESP_RCP_IF;
    assert(spi_is_stateful_packet(&skb));
    h->if_type = ESP_STA_IF;
    assert(!spi_is_stateful_packet(&skb));
    h->if_type = ESP_AP_IF;
    assert(!spi_is_stateful_packet(&skb));
    skb.len--;
    h->if_type = ESP_HCI_IF;
    assert(!spi_is_stateful_packet(&skb));
    assert(!spi_is_stateful_packet(NULL));
}

static void test_exact_dummy_rx_sentinel(void)
{
    struct esp_payload_header h = {0};
    assert(!spi_is_dummy_rx(NULL));
    h.if_type = 0xf;
    h.if_num = 0xf;
    assert(spi_is_dummy_rx(&h));
    h.if_type = ESP_STA_IF; assert(!spi_is_dummy_rx(&h)); h.if_type = 0xf;
    h.if_num = 0; assert(!spi_is_dummy_rx(&h)); h.if_num = 0xf;
    h.flags = 1; assert(!spi_is_dummy_rx(&h)); h.flags = 0;
    h.packet_type = 1; assert(!spi_is_dummy_rx(&h)); h.packet_type = 0;
    h.reserved1 = 1; assert(!spi_is_dummy_rx(&h)); h.reserved1 = 0;
    h.len = 1; assert(!spi_is_dummy_rx(&h)); h.len = 0;
    h.offset = 1; assert(!spi_is_dummy_rx(&h)); h.offset = 0;
    h.checksum = 1; assert(!spi_is_dummy_rx(&h)); h.checksum = 0;
    h.reserved2 = 1; assert(!spi_is_dummy_rx(&h)); h.reserved2 = 0;
    h.reserved3 = 1; assert(!spi_is_dummy_rx(&h)); h.reserved3 = 0;
    assert(spi_is_dummy_rx(&h));
}

int main(void)
{
    test_command_parser();
    test_stateful_classifier();
    test_exact_dummy_rx_sentinel();
    puts("PASS: production SPI command parser, HCI/RCP stateful and dummy RX sentinel");
    return 0;
}
