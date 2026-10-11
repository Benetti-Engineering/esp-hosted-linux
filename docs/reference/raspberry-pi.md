# Raspberry Pi reference setup

Raspberry Pi is a convenient development and validation host for ESP-Hosted-Linux, but it is not required. Use the generic [Hardware setup](../getting-started/hardware-setup.md), [Build, flash, and load](../getting-started/build-and-flash.md), and [Porting](../porting.md) pages for the platform-independent flow.

This page collects the Raspberry Pi-specific pin mappings, boot configuration, UART setup, and `rpi_init.sh` helper usage in one place.

## Pin numbering

Pin numbers in the tables below are **physical 40-pin header numbers**. The `rpi_init.sh` helper uses **BCM GPIO numbers** when applying the SPI Device Tree overlay (`resetgpio=`, `handshakegpio=`, `datareadygpio=`). The helper defaults to BCM6 for reset (physical pin 31), BCM22 for Handshake (pin 15), and BCM27 for Data Ready (pin 13). Direct kernel module loading does not accept a `resetpin=` parameter.

Raspberry Pi GPIO is 3.3 V logic. Do not connect ESP signals to 5 V logic.

## SPI reference wiring

Use the ESP-side signal assignments from [Hardware setup](../getting-started/hardware-setup.md#spi). On Raspberry Pi, the reference host mapping is:

| Function | Raspberry Pi physical pin |
|---|---:|
| CS0 | 24 |
| SCLK | 23 |
| MISO | 21 |
| MOSI | 19 |
| Ground | 25 |
| Handshake (ESP → host) | 15 |
| Data Ready (ESP → host) | 13 |
| ESP reset | 31 |

**Handshake and Data Ready are mandatory for SPI operation.** The helper uses BCM22 for Handshake, BCM27 for Data Ready, and BCM6 for ESP reset by default.

Enable SPI in the active Raspberry Pi `config.txt`:

```text
dtparam=spi=on
```

Recent Raspberry Pi OS images keep this file at `/boot/firmware/config.txt`; older images may use `/boot/config.txt`. Reboot after changing it.

The project helper builds and loads `spidev_disabler.dts` before inserting the ESP SPI module so `spidev` does not claim the same chip select.

## SDIO reference wiring

Use the ESP-side signal assignments and pull-up guidance from [Hardware setup](../getting-started/hardware-setup.md#sdio). On Raspberry Pi, the reference mapping is:

| Function | Raspberry Pi physical pin |
|---|---:|
| DAT3 | 13 |
| CLK | 15 |
| CMD | 16 |
| DAT0 | 18 |
| DAT1 | 22 |
| DAT2 | 37 |
| ESP reset | 31 |
| Ground | 39 |

For production SDIO recovery with host-controlled ESP EN, first install
`host/overlays/esp32-sdio-pwrseq.dtbo` into the Raspberry Pi boot overlays
directory, then enable the reset pwrseq **before** the SDIO overlay in the active
`config.txt`:

```text
dtoverlay=esp32-sdio-pwrseq
dtoverlay=sdio,poll_once=off
```

The ESP overlay marks the MMC host with `espressif,full-chip-reset`; the Linux
driver will only treat `mmc_hw_reset()` as a firmware reincarnation when that
explicit marker and a bound pwrseq are both present. Reboot after changing the
boot Device Tree. Without this overlay, SDIO remains supported and recovery uses
the generation-ACKed in-band software reboot fallback.

## USB reference connection

ESP32-S31 provides a native USB 2.0 High-Speed bulk interface. Connect the ESP32-S31 USB port directly to any available USB port on the Raspberry Pi using a standard USB cable.

- No Raspberry Pi GPIOs, Device Tree overlays, or external D+/D- pull-ups are required.
- VBUS is present on the normal USB cable; power the ESP board according to its board design.
- Ready replay and firmware restart requests are communicated in-band with USB vendor control transfers.
- Verify USB enumeration with `lsusb -d 303a:4002`.

## Bluetooth HCI over UART

If Bluetooth HCI uses UART, connect the Raspberry Pi UART to the ESP-side pins listed in [Hardware setup](../getting-started/hardware-setup.md#bluetooth-hci-over-uart).

| Signal on Raspberry Pi | Physical pin | Connect to ESP |
|---|---:|---|
| TX | 8 | ESP RX |
| RX | 10 | ESP TX |
| RTS | 11 | ESP CTS |
| CTS | 36 | ESP RTS |

Enable the UART hardware and free the onboard Bluetooth UART when the 40-pin UART is used for ESP HCI:

```text
enable_uart=1
dtoverlay=disable-bt
```

Disable the Raspberry Pi Bluetooth UART service:

```sh
sudo systemctl disable hciuart
```

Remove any `console=serial0,...` setting from the active kernel command line before using that UART for HCI. Recent Raspberry Pi OS images keep the command line in `/boot/firmware/cmdline.txt`.

Raspberry Pi 5 has different default UART routing from earlier boards. Check the active `/dev/serial0` mapping before assuming it points to physical pins 8 and 10.

## `rpi_init.sh` helper

From `host/`:

```sh
./rpi_init.sh sdio
# or
./rpi_init.sh spi
# or
./rpi_init.sh usb
```

The helper combines the common module build/load flow with Raspberry Pi-specific bus and GPIO setup. For SPI, it compiles and applies the Device Tree overlay (`overlays/esp32-spi.dtbo` and `spidev_disabler.dtbo`) using BCM6 for ESP reset, BCM22 for Handshake, and BCM27 for Data Ready unless overridden. For SDIO, it builds `overlays/esp32-sdio-pwrseq.dtbo` when `dtc` is available and, after loading the driver, waits briefly for the ESP SDIO function to bind before verifying the full-chip-reset marker on that controller ancestry; neither `dtc` nor the hardware-reset overlay is required for the acknowledged software-reboot fallback. For USB, no GPIO or Device Tree setup is required; `./rpi_init.sh usb` builds and loads `esp32_usb.ko`, and the USB core binds the device when connected.

The **default** SPI and SDIO reference mappings conflict: Raspberry Pi SDIO uses BCM22..27, while default ESP SPI uses BCM22/27 for Handshake/Data Ready, and the ESP SDIO pwrseq uses BCM6, the default SPI reset. The helper reads the live SDIO `brcm,pins` group and pwrseq reset GPIO and refuses SPI only when those boot-owned GPIOs overlap SPI0 (GPIO7..11) or the selected ESP control GPIOs. Alternate Raspberry Pi SDIO groups such as GPIO34..39 can therefore coexist with SPI when the complete GPIO sets are disjoint. Unknown/custom active SDIO pinmuxes still fail closed.

Useful arguments include:

| Argument | Purpose |
|---|---|
| `ap_support` | Build with access-point support |
| `btuart` | Configure Raspberry Pi pins for 4-wire HCI UART |
| `btuart_2pins` | Configure Raspberry Pi TX/RX pins for HCI UART without hardware flow control |
| `resetgpio=<BCM-number>` | Override ESP reset GPIO in SPI Device Tree overlay; default is BCM6 (`resetpin=` is accepted as an alias) |
| `handshakegpio=<BCM-number>` | Override Handshake GPIO in SPI Device Tree overlay; default is BCM22 |
| `datareadygpio=<BCM-number>` | Override Data Ready GPIO in SPI Device Tree overlay; default is BCM27 |
| `rawtp_host_to_esp` | Run raw host-to-ESP transport traffic |
| `rawtp_esp_to_host` | Run raw ESP-to-host transport traffic |
| `ota_file=/path/to/firmware.bin` | Send a firmware image to ESP |

Run `./rpi_init.sh --help` for the complete argument list.

### Select hosted Bluetooth or Thread

`rpi_init.sh` loads the selected transport module with the default secondary-radio request (`none`). After bring-up, select hosted Bluetooth, Thread RCP, or both through sysfs:

```sh
# USB example
echo bt+154 | sudo tee /sys/module/esp32_usb/parameters/radio_service
cat /sys/module/esp32_usb/parameters/radio_service_active
```

Use `esp32_spi` or `esp32_sdio` in the path for those transports.

## Verify bring-up

After loading the driver:

```sh
iw dev
ip link
lsmod | grep esp32
```

If the ESP interface does not appear, save `dmesg` and the ESP serial log and continue with [Troubleshooting](../troubleshooting.md).
