#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Build the pinned quad controller support against the running Pi kernel.
set -euo pipefail

helper_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
kernel_release="${KERNEL_RELEASE:-$(uname -r)}"
kernel_mm="$(printf '%s' "$kernel_release" | sed -n 's/^\([0-9]*\.[0-9]*\).*/\1/p')"
kdir="${KDIR:-/lib/modules/$kernel_release/build}"
export CACHE_DIR="${CACHE_DIR:-$HOME/.cache/esp-hosted-rpi5-spi-hd}"
repo="$CACHE_DIR/linux"
out="${SPI_DW_OUT_DIR:-$CACHE_DIR/qspi-modules-$kernel_release}"
obj="${SPI_DW_WORK_DIR:-$CACHE_DIR/qspi-obj-$kernel_release}"
quad_ref=81a76dd2284e09547cc5a9eeb88b174fea5a819a
test -d "$kdir"
mkdir -p "$CACHE_DIR" "$out" "$obj"
if [[ ! -d "$repo/.git" ]]; then
    git clone --filter=blob:none --depth=1 --branch "rpi-$kernel_mm.y" \
        https://github.com/raspberrypi/linux.git "$repo"
fi
if ! git -C "$repo" cat-file -e "$quad_ref^{commit}" 2>/dev/null; then
    git -C "$repo" fetch --no-tags --depth=2 origin "$quad_ref"
fi
# The staging helper reads git objects; it never resets or patches this checkout.
source_log="$(python3 "$helper_dir/prepare-rp1-quad-source.py")"
printf '%s\n' "$source_log"
src="$(printf '%s\n' "$source_log" | tail -n 1)"
test -s "$src/drivers/spi/spi-dw-core.c"
for name in spi-dw-core.c spi-dw-dma.c spi-dw-mmio.c spi-dw.h internals.h; do
    if ! cmp -s "$src/drivers/spi/$name" "$obj/$name"; then
        cp "$src/drivers/spi/$name" "$obj/$name"
    fi
done
cat > "$obj/Makefile.new" <<'EOF'
obj-m += spi-dw.o
spi-dw-y := spi-dw-core.o
spi-dw-$(CONFIG_SPI_DW_DMA) += spi-dw-dma.o
obj-m += spi-dw-mmio.o
EOF
if ! cmp -s "$obj/Makefile.new" "$obj/Makefile"; then
    mv "$obj/Makefile.new" "$obj/Makefile"
else
    rm "$obj/Makefile.new"
fi
make -C "$kdir" M="$obj" modules
cp "$obj/spi-dw.ko" "$obj/spi-dw-mmio.ko" "$out/"
printf 'Built controller modules: %s\n' "$out"

if [[ "${1:-}" == --load ]]; then
    # Replacing RP1 modules is only safe if every pre-existing module can be
    # restored. Validate build compatibility before touching live devices.
    run_root() {
        if [[ "$EUID" -eq 0 ]]; then "$@"; else sudo -n "$@"; fi
    }
    list_overlays() { run_root dtoverlay -l; }
    module_loaded() { grep -qw "$1" /proc/modules; }

    if [[ "$kernel_release" != "$(uname -r)" ]]; then
        echo "Cannot load modules for $kernel_release onto $(uname -r)" >&2
        exit 1
    fi
    krel_file="$kdir/include/config/kernel.release"
    if [[ -r "$krel_file" && "$(cat "$krel_file")" != "$kernel_release" ]]; then
        echo "Kernel build tree release does not match running kernel" >&2
        exit 1
    fi
    for name in spi-dw spi-dw-mmio; do
        vermagic="$(modinfo -F vermagic "$out/$name.ko")"
        if [[ "$vermagic" != "$kernel_release "* ]]; then
            echo "$name vermagic mismatch: $vermagic" >&2
            exit 1
        fi
    done

    rollback_dir="$(mktemp -d "$out/.spi-dw-rollback-XXXXXXXX")"
    rollback_needed=0
    rollback_on_exit() {
        local rc=$?
        trap - EXIT
        if [[ "$rollback_needed" == 1 ]]; then
            echo "RP1 replacement failed (exit=$rc); restoring original modules" >&2
            run_root rmmod spi_dw_mmio 2>/dev/null || true
            run_root rmmod spi_dw 2>/dev/null || true
            if [[ -f "$rollback_dir/spi-dw.ko" ]]; then
                run_root insmod "$rollback_dir/spi-dw.ko" ||
                    echo "CRITICAL: spi_dw restore failed; snapshot: $rollback_dir" >&2
            fi
            if [[ -f "$rollback_dir/spi-dw-mmio.ko" ]]; then
                run_root insmod "$rollback_dir/spi-dw-mmio.ko" ||
                    echo "CRITICAL: spi_dw_mmio restore failed; snapshot: $rollback_dir" >&2
            fi
            echo "Rollback snapshot retained: $rollback_dir" >&2
        else
            rm -rf -- "$rollback_dir"
        fi
        return "$rc"
    }
    trap rollback_on_exit EXIT

    # modinfo -n may name a different installed module than the custom .ko
    # currently loaded. Verify srcversion before trusting a rollback image.
    for name in spi_dw spi_dw_mmio; do
        if ! module_loaded "$name"; then continue; fi
        loaded_version="$(cat "/sys/module/$name/srcversion" 2>/dev/null || true)"
        [[ -n "$loaded_version" ]] || {
            echo "Cannot verify active $name provenance; refusing teardown" >&2
            exit 1
        }
        installed_path="$(modinfo -n "$name" 2>/dev/null || true)"
        # Kernel module names use underscores; kbuild emits hyphenated .ko
        # filenames. A nonexistent underscore path previously rejected the
        # exact matching rollback image even when it was in $out.
        filename="${name//_/-}.ko"
        chosen=""
        # The runner's verified previous controller lives outside the new
        # build directory. The frozen benchmark's restore helper uses this
        # known-good cache, so include it before relying on any staged output.
        for candidate in "$CACHE_DIR/modules-$kernel_release/$filename" \
                         "$out/$filename" "$obj/$filename" "$installed_path"; do
            [[ -f "$candidate" ]] || continue
            if [[ "$(modinfo -F srcversion "$candidate" 2>/dev/null)" == "$loaded_version" ]]; then
                chosen="$candidate"
                break
            fi
        done
        [[ -n "$chosen" ]] || {
            echo "No rollback image matches live $name srcversion $loaded_version" >&2
            exit 1
        }
        cp -- "$chosen" "$rollback_dir/$filename"
    done

    for name in esp32-spi-hd-rpi5 esp32-spi spidev_disabler; do
        id="$(list_overlays | awk -F: -v name="$name" '
            { rest=$2; sub(/^[[:space:]]+/, "", rest); split(rest, a, /[[:space:]]+/)
              if (a[1] == name) { gsub(/[[:space:]]/, "", $1); print $1; exit } }')"
        if [[ -n "$id" ]]; then run_root dtoverlay -r "$id"; fi
    done
    for name in esp32-spi-hd-rpi5 esp32-spi spidev_disabler; do
        if list_overlays | awk -F: -v name="$name" '
            { rest=$2; sub(/^[[:space:]]+/, "", rest); split(rest, a, /[[:space:]]+/)
              if (a[1] == name) found=1 }
            END { exit !found }'; then
            echo "Failed to remove overlay $name; refusing module replacement" >&2
            exit 1
        fi
    done
    for name in esp32_spi_hd spi_dw_mmio spi_dw; do
        if module_loaded "$name"; then
            run_root rmmod "$name"
            if [[ "$name" == spi_dw_mmio || "$name" == spi_dw ]]; then
                rollback_needed=1
            fi
        fi
    done
    rollback_needed=1
    run_root insmod "$out/spi-dw.ko"
    run_root insmod "$out/spi-dw-mmio.ko"
    test "$(cat /sys/module/spi_dw/srcversion)" = "$(modinfo -F srcversion "$out/spi-dw.ko")"
    test "$(cat /sys/module/spi_dw_mmio/srcversion)" = "$(modinfo -F srcversion "$out/spi-dw-mmio.ko")"
    rollback_needed=0
fi
