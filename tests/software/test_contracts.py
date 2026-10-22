"""Source-backed CI/transport surface checks. Not runtime correctness proof."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ("sdio", "spi", "usb", "spi_hd")

def read(rel):
    return (ROOT / rel).read_text()

def quality_targets(src):
    # The quality script must include all transports in every tool mode.
    return [set(block.split()) for block in re.findall(
        r"for transport in ([\w ]+); do", src)]

class SourceContractTests(unittest.TestCase):
    def test_quality_has_every_transport_in_every_mode(self):
        loops = quality_targets(read(".gitlab/ci/scripts/linux-quality.sh"))
        self.assertEqual(len(loops), 3)
        for loop in loops:
            self.assertEqual(loop, set(TARGETS))

    def test_negative_quality_fixture_detected(self):
        src = read(".gitlab/ci/scripts/linux-quality.sh")
        altered = src.replace("for transport in sdio spi usb spi_hd; do",
                              "for transport in sdio spi usb; do", 1)
        self.assertNotEqual(quality_targets(altered), quality_targets(src))

    def test_host_firmware_mirrors_are_byte_identical(self):
        # Independently enforce the existing validate_mirrored_files job's
        # contract during local source_contracts runs, before long builds.
        for filename in ("adapter.h", "esp_fw_version.h"):
            with self.subTest(mirrored_header=filename):
                host = ROOT / "host/include" / filename
                firmware = ROOT / "esp/esp_driver/network_adapter/main/include" / filename
                self.assertEqual(host.read_bytes(), firmware.read_bytes(),
                                 "host/firmware mirror drift in " + filename)

    def test_gitlab_kernel_job_scripts_use_explicit_bash(self):
        # Running .sh directly requires Git index executable bits to remain
        # intact across branch copies. Bash interpretation is portable even
        # when CI checkouts preserve only regular file read permissions.
        linux = read(".gitlab/ci/linux.yml")
        cross = read(".gitlab/ci/software-cross-arch.yml")
        self.assertIn('bash .gitlab/ci/scripts/linux-build.sh "$KERNEL_VERSION"', linux)
        self.assertEqual(linux.count("bash .gitlab/ci/scripts/linux-quality.sh "), 3)
        self.assertIn('bash .gitlab/ci/scripts/linux-build.sh "$KERNEL_VERSION"', cross)

    def test_compatibility_build_includes_four(self):
        src = read(".gitlab/ci/scripts/linux-build.sh")
        for t in TARGETS:
            self.assertRegex(src, rf"build_transport\s+{t}\b")

    def test_host_makefile_supports_four(self):
        src = read("host/Makefile")
        for t in TARGETS:
            self.assertIn("ifeq ($(target), " + t + ")", src)

    def test_kernel_versions_and_plan_match(self):
        src = read(".gitlab/ci/linux.yml")
        actual = re.findall(r'KERNEL_VERSION:\s*"([0-9.]+)"', src)
        plan = json.loads(read(".gitlab/ci/software/coverage-plan.json"))
        self.assertEqual(actual, plan["existing_images"]["kernel_versions"])
        self.assertEqual(set(plan["transports"]), set(TARGETS))
        self.assertTrue(all(x["kind"] == "runtime" for x in plan["future_images"]))
        self.assertEqual(
            {x["id"] for x in plan["future_images"] if x["status"] == "NOT_BUILT"},
            {"x86-6.12-kunit-uml", "x86-6.12-dummy-hcd", "arm64-6.12-debug-qemu"})

    def test_framework_gitlab_opt_in_no_new_image(self):
        ci = read(".gitlab-ci.yml")
        job = read(".gitlab/ci/software-framework.yml")
        self.assertIn(".gitlab/ci/software-framework.yml", ci)
        self.assertIn("CI_PIPELINE_SOURCE", job)
        self.assertIn("tests/software/**/*", job)
        self.assertIn("when: never", job)
        self.assertNotIn("needs: []", job)
        self.assertIn('image: "$LINUX_IMAGE_6_12"', job)
        self.assertNotIn("CI_SOFTWARE_EXTENDED", job)

    def test_coverage_is_explicitly_unqualified(self):
        manifest = json.loads(read(".gitlab/ci/software/coverage-plan.json"))
        self.assertEqual(set(manifest["transports"]), set(TARGETS))
        self.assertTrue(manifest["software_unimplemented"])
        for name, info in manifest["transports"].items():
            with self.subTest(target=name):
                self.assertTrue(info["planned"])
        # Keep the declared implementation ledger exact, including the
        # production wire-span guard work added after the initial CI design.
        implemented = set(manifest["software_implemented"])
        self.assertEqual(implemented,
                         {"source_contracts", "shared_wire_abi_native",
                          "production_wire_span_guard_four_backends",
                          "production_wire_span_native",
                          "kernel_module_artifact_abi_audit",
                          "sdio_production_rx_counter_extracted",
                          "sdio_dma_safe_persistent_buffer_policy",
                          "usb_production_stream_parser_extracted",
                          "spi_hd_production_batch_ack_extracted",
                          "spi_production_cmd_stateful_dummy_extracted",
                          "usb_stream_fragment_coalesce_resync_mps_extracted",
                          "spi_hd_batch_ack_predicates_extracted",
})
        self.assertTrue(implemented.isdisjoint(manifest["software_unimplemented"]))

    def test_cross_compile_selects_cross_toolchain(self):
        build = read(".gitlab/ci/scripts/linux-build.sh")
        self.assertIn('CC_CMD="${CC_CMD:-${CROSS_COMPILE}gcc}"', build)
        cross = read(".gitlab/ci/software-cross-arch.yml")
        for t in ("armv7-4.9-4k", "armv7-6.1-4k",
                  "arm64-6.12-4k", "arm64-6.12-16k", "arm64-6.12-64k"):
            self.assertIn("host:" + t + ":", cross)
        images = read(".gitlab/ci/arm-images.yml")
        self.assertIn('CI_CROSS_SDK_OCI_PLATFORM: "amd64"', images)
        self.assertIn('CI_CROSS_SDK_RUNNER_TAG: "x86_64"', images)
        self.assertIn("CI_CROSS_SDK_RUNNER_TAG", cross)
        self.assertIn("CI_CROSS_SDK_PROVENANCE", cross)
        self.assertNotIn("CI_ARM64_RUNNER_READY", cross)
        self.assertIn("verify_sdk.py", cross)
        self.assertIn("linux-build.sh", cross)

    def test_production_guard_used_by_all_four_backends(self):
        for target, path in {
            "sdio": "host/sdio/esp_sdio.c",
            "spi": "host/spi/esp_spi.c",
            "usb": "host/usb/esp_usb.c",
            "spi_hd": "host/spi_hd/esp_spi_hd.c",
        }.items():
            with self.subTest(transport=target):
                self.assertIn('#include "esp_host_wire_bounds.h"', read(path))
                self.assertIn("esp_host_wire_span_valid(", read(path))
        guard = read("host/include/esp_host_wire_bounds.h")
        self.assertIn("payload_len > available - offset", guard)

    def test_mutation_of_real_wire_guard_is_caught(self):
        import os
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            shadow = Path(tmp) / "esp_host_wire_bounds.h"
            code = read("host/include/esp_host_wire_bounds.h")
            original = "if (!payload_len || !ESP_OFFSET_VALID(offset))"
            self.assertIn(original, code)
            shadow.write_text(code.replace(original,
                                           "if (0 && !ESP_OFFSET_VALID(offset))", 1))
            binary = Path(tmp) / "wire-mutant"
            compiler = os.environ.get("CC", "gcc").split()
            build = subprocess.run(compiler + [
                "-std=c11", "-I", tmp, "-I", str(ROOT / "host/include"),
                str(ROOT / "tests/software/wire_abi.c"), "-o", str(binary)
            ], capture_output=True, text=True, timeout=80)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            # A real broken wire guard must violate the native property oracle.
            outcome = subprocess.run([str(binary)], capture_output=True, timeout=80)
            self.assertNotEqual(outcome.returncode, 0,
                                "mutant unexpectedly passed production property tests")

    def test_checksum_uses_one_path_in_sparse_and_production(self):
        # No analyzer/test-only implementation: the production function must
        # expand identically with and without Sparse's __CHECKER__ define.
        import subprocess
        src = read("host/include/adapter.h")
        start = src.index("static inline uint16_t compute_checksum(")
        body = src[start:].rsplit("\n#endif", 1)[0]
        self.assertNotIn("#ifdef __CHECKER__", body)
        self.assertNotIn("__builtin_assume_aligned", body)
        self.assertIn("__builtin_memcpy(&word, buf, sizeof(word));", body)
        source = "#include <stdint.h>\n" + body + "\n"
        outputs = []
        for checker in (False, True):
            with self.subTest(sparse_checker=checker):
                cmd = ["gcc", "-E", "-P", "-x", "c"]
                if checker:
                    cmd.append("-D__CHECKER__")
                cmd.append("-")
                run = subprocess.run(cmd, input=source, text=True,
                                     capture_output=True, timeout=15)
                self.assertEqual(run.returncode, 0, run.stderr)
                outputs.append(run.stdout)
        self.assertEqual(outputs[0], outputs[1])

    def test_transport_interface_surfaces_exist(self):
        needles = {
            "sdio": ("sdio_claim_host(", "sdio_release_host(", "ESP_SLAVE_CMD53_END_ADDR"),
            "spi": ("spi_sync_transfer(", "handshake_gpio", "data_ready_gpio"),
            "usb": ("usb_submit_urb(", "usb_kill_urb(", "esp_usb_ingest_stream"),
            "spi_hd": ("spi_sync_transfer(", "spi_max_transfer_size(", "SPIHD_CMD_RDDMA"),
        }
        plan = json.loads(read(".gitlab/ci/software/coverage-plan.json"))
        for target, symbols in needles.items():
            source = read(plan["transports"][target]["source"])
            for needle in symbols:
                with self.subTest(target=target, needle=needle):
                    self.assertIn(needle, source)

    def test_negative_source_fixture_detected(self):
        src = read("host/usb/esp_usb.c")
        self.assertIn("usb_submit_urb(", src)
        # 'deleted_usb_submit_urb(' still contains the literal original
        # substring, so count() cannot detect that mutation. Match only
        # complete function identifiers and remove one call from the fixture.
        call = r"\busb_submit_urb\("
        baseline_count = len(re.findall(call, src))
        self.assertGreater(baseline_count, 0)
        injected, replaced = re.subn(call, "disabled_submit(", src, count=1)
        self.assertEqual(replaced, 1)
        self.assertEqual(len(re.findall(call, injected)), baseline_count - 1)

if __name__ == "__main__":
    unittest.main()
