// SPDX-License-Identifier: Apache-2.0
// Copyright 2015-2022 Espressif Systems (Shanghai) PTE LTD
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//

#ifndef __NETWORK_ADAPTER_PRIV__H
#define __NETWORK_ADAPTER_PRIV__H

#include <stdbool.h>
#include "esp_err.h"
#include "adapter.h"

typedef struct {
    interface_context_t *context;
} adapter;

struct wow_config {
    uint8_t any;
    uint8_t disconnect;
    uint8_t magic_pkt;
    uint8_t four_way_handshake;
    uint8_t eap_identity_req;
};

bool esp_hosted_wifi_channel_transition_active(void);
bool esp_hosted_monitor_is_enabled(void);
uint8_t esp_hosted_monitor_channel(void);
void esp_hosted_monitor_snapshot_channel(void);
bool esp_hosted_monitor_channel_allowed(uint8_t requested, bool radio_transition);
esp_err_t esp_hosted_monitor_restore(void);
esp_err_t esp_hosted_monitor_config(bool enable, uint8_t channel);

#endif
