#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Capture transport configuration and existing logs without changing the device.
set -euo pipefail

module_path=/sys/module/esp32_spi_hd
output=${1:-qspi-debug-$(date -u +%Y%m%dT%H%M%SZ)}
kernel_log=${2:-}
if [[ ! -d "$module_path" ]]; then
    echo 'esp32_spi_hd is not loaded.' >&2
    exit 1
fi
mkdir -- "$output"

{
    date -u
    uname -a
    if [[ -r /sys/firmware/devicetree/base/model ]]; then
        tr '\0' '\n' </sys/firmware/devicetree/base/model
    fi
    modinfo esp32_spi_hd 2>/dev/null || true
    for attribute in version srcversion taint coresize initsize; do
        [[ -r "$module_path/$attribute" ]] || continue
        printf '%s=' "$attribute"
        cat "$module_path/$attribute"
    done
} >"$output/system.txt"

shopt -s nullglob
for parameter in "$module_path"/parameters/spi_hd_* \
                 "$module_path"/parameters/clockspeed \
                 "$module_path"/parameters/raw_tp_mode; do
    [[ -r "$parameter" ]] || continue
    if value=$(cat "$parameter" 2>/dev/null); then
        printf '%s=%s\n' "${parameter##*/}" "$value" >>"$output/parameters.txt"
    fi
done
if [[ -r /sys/kernel/debug/esp32/log_level ]]; then
    cat /sys/kernel/debug/esp32/log_level >"$output/log-level.txt"
fi

for device in /sys/bus/spi/devices/*; do
    [[ -L "$device/driver" ]] || continue
    driver=$(readlink -f "$device/driver")
    [[ ${driver##*/} == esp_spi_hd ]] || continue
    name=${device##*/}
    controller=$(dirname "$(readlink -f "$device")")
    {
        printf 'device=%s\ncontroller=%s\n' "$device" "$controller"
        for statistics in "$device"/statistics/* "$controller"/statistics/*; do
            [[ -r "$statistics" ]] || continue
            printf '%s=' "$statistics"
            cat "$statistics"
        done
        for property in compatible spi-max-frequency spi-tx-bus-width \
                        spi-rx-bus-width spi-cpol spi-cpha reset-gpios data-ready-gpios; do
            node="$device/of_node/$property"
            [[ -r "$node" ]] || continue
            printf '%s (DT bytes, hex): ' "$property"
            od -An -tx1 "$node"
        done
    } >"$output/$name.txt"
done
if [[ -n "$kernel_log" ]]; then
    cat -- "$kernel_log" >"$output/dmesg.txt"
elif ! dmesg --color=never >"$output/dmesg.txt" 2>"$output/dmesg-error.txt"; then
    echo 'Kernel log capture failed; run with permission to read dmesg.' >&2
    exit 1
fi
echo "Captured SPI-HD diagnostics in $output"
