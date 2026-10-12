# Wi-Fi monitor mode

ESP-Hosted exposes Linux Wi-Fi monitor mode through cfg80211. Captured frames use a dedicated Hosted monitor record and are delivered to a Linux monitor netdev with a radiotap header; they are not converted to Ethernet frames or mixed with the normal STA/AP data path.

## Supported targets and transports

Monitor RX is implemented in the common Wi-Fi firmware/host path and is available for the Wi-Fi-capable product configurations built by this repository:

| ESP target | Monitor-capable hosted transports |
|---|---|
| ESP32 | SDIO, SPI |
| ESP32-S2 | SPI |
| ESP32-S3 | SPI |
| ESP32-S31 | SPI, USB |
| ESP32-C2 | SPI |
| ESP32-C3 | SPI |
| ESP32-C5 | SDIO, SPI |
| ESP32-C6 | SDIO, SPI |
| ESP32-C61 | SDIO, SPI |

A target advertises `NL80211_IFTYPE_MONITOR` only when the connected firmware reports the Hosted monitor capability.

## Create a monitor interface

Find the ESP-Hosted PHY and create a monitor interface:

```sh
iw phy
sudo iw phy phy0 interface add mon0 type monitor
sudo ip link set mon0 up
sudo iw dev mon0 set channel 6
```

Capture with tcpdump:

```sh
sudo tcpdump -i mon0 -s 0 -nn -e
```

or write a pcap for Wireshark:

```sh
sudo tcpdump -i mon0 -s 0 -w monitor.pcap
```

Stop and remove the interface:

```sh
sudo ip link set mon0 down
sudo iw dev mon0 del
```

Only one monitor virtual interface is supported per ESP-Hosted radio.

## Channel behavior and coexistence

ESP Wi-Fi uses one radio, so monitor mode cannot independently receive on a second channel while an active STA or AP remains on another channel.

- **Monitor only:** bringing the monitor interface UP starts capture on channel 1 if no channel has been selected yet; then `iw dev mon0 set channel <channel>` programs the requested channel. Linux cfg80211 requires a monitor interface to be running before `.set_monitor_channel` is called.
- **STA/AP plus monitor on the same channel:** supported by the common monitor path. If STA/AP is already active when `mon0` is brought UP, firmware inherits that shared radio channel automatically; no separate monitor retune is required.
- **Monitor channel different from an active STA/AP channel:** rejected instead of silently retuning the associated interface. Linux may reject a monitor channel change earlier with `EBUSY` while a non-monitor interface is running; this is consistent with the single-radio rule.
- **Scanning while monitor is active:** an explicitly same-channel scan is allowed; wildcard or off-channel scans are rejected because they would retune the single physical radio during capture.
- **Channel width:** monitor channel requests currently accept 20 MHz / 20 MHz no-HT channel definitions. Wider requested channel definitions are rejected.

Changing the monitor channel while the monitor interface is UP reprograms firmware only after the coexistence checks pass. On Linux 6.1, cfg80211 permits that operation only while the running interfaces are monitor-only; with an active STA/AP, monitor capture follows the already-owned radio channel.

## Captured frames

The firmware uses the ESP-IDF promiscuous RX API and forwards management, control, and data MPDUs. ESP-IDF `WIFI_PKT_MISC` reports are not exposed as Linux monitor frames because they do not contain a normal 802.11 payload.

The 802.11 bytes are preserved as supplied by ESP-IDF. The firmware prepends a versioned, packed internal monitor metadata header; the Linux driver validates that metadata and replaces it with radiotap before delivering the skb to the monitor netdev.

## Radiotap metadata

The driver reports only metadata supplied reliably by the pinned ESP-IDF target API.

| Radiotap information | Behavior |
|---|---|
| Channel / frequency | Reported from the promiscuous RX channel |
| RSSI | Reported as dBm antenna signal |
| Legacy rate | Reported from the legacy RX descriptor family where ESP-IDF documents `rate` as PHY-rate encoding. HE-family descriptors do not currently export radiotap RATE because their `rate` field has format-dependent 11b/L-SIG semantics. |
| HT MCS / bandwidth / GI | Reported on targets whose ESP-IDF RX metadata exposes those fields |
| Antenna | Reported only where ESP-IDF provides an antenna index |
| FCS present | Reported when the target metadata establishes that FCS bytes are present |
| Bad FCS | Reserved in the Hosted metadata; not asserted unless firmware can establish it |
| Timestamp / TSFT | The firmware metadata carries the ESP-IDF local RX timestamp for diagnostics, but Linux does not label it as radiotap TSFT because it is not guaranteed to be an 802.11 TSF value |

The ESP-IDF promiscuous RX control descriptor is target-dependent. Legacy Wi-Fi targets use the older `wifi_pkt_rx_ctrl_t` layout, while HE-capable targets alias it to `esp_wifi_rxctrl_t`; ESP-IDF further selects the HE layout by Wi-Fi MAC version. ESP-Hosted therefore reads the target-compiled named fields instead of treating the descriptor as a common raw byte layout. Fields that are not semantically equivalent across descriptor families are left unavailable rather than guessed. The CCK/OFDM modulation class is normalized separately: legacy descriptors derive CCK from the documented PHY-rate enum, while HE descriptors derive it from `cur_bb_format`, so radiotap channel flags remain correct even when HE `rate` is intentionally not exported.

New metadata can be added by extending the internal monitor metadata version instead of changing the meaning of existing fields.

## Backpressure and drops

Sniffer traffic can exceed the host transport bandwidth. Monitor RX therefore uses the existing bounded low-priority firmware transport queue and never blocks the Wi-Fi receive callback waiting for host capacity.

When overloaded, monitor frames are dropped rather than allowing the monitor stream to corrupt or permanently starve normal Wi-Fi control/data traffic. Firmware logs periodically report `MONITOR_DROP` counters for queue-full, allocation, and oversize drops. Linux also accounts monitor RX drops/malformed records in the monitor device/adapter statistics.

A dropped monitor frame is expected overload behavior; malformed Hosted records are rejected.

## Lifecycle and recovery

Monitor enable/disable is reversible. Bringing `mon0` UP enables the firmware promiscuous callback; bringing it DOWN disables capture. Deleting the interface tears down the monitor netdev. An in-place firmware-only reboot keeps the same bound Linux device and retains the existing `wiphy` and monitor netdev. Capture pauses while firmware and WLAN endpoints are reconstructed; when the new firmware is ready, the driver reopens the same monitor netdev if it was previously running. A full transport disconnect/remove/reprobe unregisters the old `wiphy` and destroys `mon0`; the driver clears its saved monitor intent and does **not** recreate `mon0` on the new binding. Userspace can create a new monitor interface explicitly after verifying that `wlan0` is ready.

Normal STA/AP operation remains independent of monitor interface creation. If the ordinary WLAN interface is stopped while monitor mode is active, the firmware Wi-Fi engine remains running for monitor capture and is stopped after the last monitor user goes away.

## Packet injection

Monitor TX injection is **not supported** by this feature. The monitor netdev is receive-only and drops transmitted skbs. Raw 802.11 injection requires a separate transmit design and capability contract and is intentionally not implied by monitor RX support.
