/* SPDX-License-Identifier: GPL-2.0-only OR Apache-2.0
 *
 * Validate the bounds of an ESP-Hosted wire frame against an available span.
 * Reject zero payloads, invalid offsets and truncated frames.
 * Callers must separately validate interface types and record semantics.
 */
#ifndef ESP_HOST_WIRE_BOUNDS_H
#define ESP_HOST_WIRE_BOUNDS_H
#include "adapter.h"

/* Reject before any subtraction or addition can overflow. */
static inline int esp_host_wire_span_valid(unsigned int payload_len,
                                          unsigned int offset,
                                          size_t available,
                                          size_t *frame_len)
{
    if (!payload_len || !ESP_OFFSET_VALID(offset))
        return 0;
    if (offset > available || payload_len > available - offset)
        return 0;
    if (frame_len)
        *frame_len = (size_t)offset + payload_len;
    return 1;
}
#endif
