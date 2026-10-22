/* Actual esp_spi_hd.c pure ACK/batching functions injected by generator.
 * Only logical fastpath/ACK gates; no DMA, QIO bus, IRQ or recovery tested.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define READ_ONCE(v) (v)

static bool spi_hd_wrdma_batch_end;
static bool spi_hd_force_sio_wrend;
static bool spi_hd_qio_tx_word32;
static bool spi_hd_qio_addr_single;
static bool spi_hd_rddma_batch_end;
static bool spi_hd_force_sio_control_e2h;
static bool spi_hd_qio_rx_word32;
static bool spi_hd_rx_batch_control;
static bool spi_hd_append_tx;
static bool spi_hd_append_no_ack;
static u32 spihd_rx_limit = 1600;

/* GENERATED_SPIDH_FUNCTIONS */

static void reset_config(void)
{
    spi_hd_wrdma_batch_end = false;
    spi_hd_force_sio_wrend = false;
    spi_hd_qio_tx_word32 = false;
    spi_hd_qio_addr_single = false;
    spi_hd_rddma_batch_end = false;
    spi_hd_force_sio_control_e2h = false;
    spi_hd_qio_rx_word32 = false;
    spi_hd_rx_batch_control = false;
    spi_hd_append_tx = false;
    spi_hd_append_no_ack = false;
    spihd_rx_limit = 1600;
}

static void test_wrdma_batch_gating(void)
{
    reset_config();
    spi_hd_wrdma_batch_end = true;
    spi_hd_force_sio_wrend = true;
    spi_hd_qio_tx_word32 = true;
    spi_hd_qio_addr_single = true;
    assert(spihd_combined_wrdma(260, 4));
    assert(!spihd_combined_wrdma(256, 4));
    assert(!spihd_combined_wrdma(258, 4));
    assert(!spihd_combined_wrdma(260, 1));
    spi_hd_qio_tx_word32 = false;
    assert(!spihd_combined_wrdma(260, 4));
    spi_hd_qio_tx_word32 = true;
    spi_hd_force_sio_wrend = false;
    assert(!spihd_combined_wrdma(260, 4));
}

static void test_rddma_batch_gating(void)
{
    reset_config();
    spi_hd_rddma_batch_end = true;
    spi_hd_force_sio_control_e2h = true;
    spi_hd_qio_rx_word32 = true;
    assert(spihd_combined_rddma(260, 4));
    assert(!spihd_combined_rddma(256, 4));
    assert(!spihd_combined_rddma(259, 4));
    assert(!spihd_combined_rddma(260, 1));
    spi_hd_force_sio_control_e2h = false;
    assert(!spihd_combined_rddma(260, 4));
}

static void test_rx_ack_batch_suppression(void)
{
    reset_config();
    spi_hd_rx_batch_control = true;
    spi_hd_rddma_batch_end = true;
    spi_hd_force_sio_control_e2h = true;
    spi_hd_qio_rx_word32 = true;
    assert(spihd_batch_rx_ack(260, 4));
    spi_hd_append_tx = true;
    spi_hd_append_no_ack = true;
    assert(!spihd_batch_rx_ack(260, 4));
    spi_hd_append_no_ack = false;
    assert(spihd_batch_rx_ack(260, 4));
    spi_hd_rx_batch_control = false;
    assert(!spihd_batch_rx_ack(260, 4));
}

static void test_ack_required_fail_closed(void)
{
    reset_config();
    assert(spihd_rx_ack_required(0, 1));
    spi_hd_append_tx = true;
    spi_hd_append_no_ack = true;
    assert(!spihd_rx_ack_required(0, 1));
    assert(!spihd_rx_ack_required(0, spihd_rx_limit));
    assert(spihd_rx_ack_required(0, 0));
    assert(spihd_rx_ack_required(0, spihd_rx_limit + 1));
    assert(spihd_rx_ack_required(1, 1));
    spi_hd_append_tx = false;
    assert(spihd_rx_ack_required(0, 1));
}

int main(void)
{
    test_wrdma_batch_gating();
    test_rddma_batch_gating();
    test_rx_ack_batch_suppression();
    test_ack_required_fail_closed();
    puts("PASS: production SPI-HD WRDMA/RDDMA batching and ACK gating");
    return 0;
}
