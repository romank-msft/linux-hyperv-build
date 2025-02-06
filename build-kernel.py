#!/usr/bin/env python3
__author__ = "romank@linux.microsoft.com"
__version__ = "0.0.1"
__license__ = "MIT"

import os
import sys
import platform

import argparse
import subprocess
import shutil
import logging
from pathlib import Path

log = logging.getLogger("build-kernel")
log_format = "[%(asctime)s][%(levelname)-8s][%(name)-8s] %(message)s"

PARALLELISM_MULTIPLIER = 4

class KernelBuilder:
    def __init__(self, arch, linux_src, build_dir, out_dir, config_file, redirect_stdout, build_modules):
        self.arch = arch
        self.linux_src = linux_src
        self.build_dir = build_dir
        self.out_dir = out_dir
        self.config_file = config_file
        self.redirect_stdout = redirect_stdout
        self.build_modules = build_modules

    def build_kernel(self):
        if "Linux" not in platform.platform():
            raise Exception("This script is intended to be run on Linux")

        targets = ["vmlinux", "headers_install"]
        if self.build_modules:
            targets.extend(["modules", "modules_install"])

        makeargs = ["-j", str(PARALLELISM_MULTIPLIER*os.cpu_count()),
                    f"ARCH={self.arch}",
                    f"INSTALL_MOD_PATH={self.out_dir}/modules",
                    f"INSTALL_HDR_PATH={self.out_dir}/headers"
        ]

        objcopy = "objcopy"
        if self.arch == "x86_64":
            if platform.machine() != "x86_64":
                makeargs += ["CROSS_COMPILE=x86_64-linux-gnu-"]
                objcopy = "x86_64-linux-gnu-objcopy"
            targets += ["bzImage"]
        elif self.arch == "arm64":
            if platform.machine() != "aarch64":
                makeargs += ["CROSS_COMPILE=aarch64-linux-gnu-"]
                objcopy = "aarch64-linux-gnu-objcopy"
            targets += ["Image"]
        else:
            raise Exception("unsupported arch")

        for target in targets:
            log.info(f"Building target {target}...")
            stdout = None if not self.redirect_stdout else subprocess.PIPE
            result = subprocess.run(["make", *makeargs, target],
                           stdout=stdout, check=True, cwd=self.linux_src)
            log.info("Build result: %s", result.returncode)

            if self.redirect_stdout:
                with open(f"{self.build_dir}/build-{target}.log", "wb") as file:
                    file.write(result.stdout)

        if "vmlinux" in targets:
            log.info("Stripping and compressing kernel debug info...")

            shutil.copy(f"{self.build_dir}/vmlinux", self.out_dir)

            vmlinux_path = f"{self.out_dir}/vmlinux"
            vmlinux_dbg = f"{self.out_dir}/vmlinux.dbg"
            subprocess.run([objcopy, "--only-keep-debug", "--compress-debug-sections", vmlinux_path, vmlinux_dbg], check=True)
            subprocess.run([objcopy, "--strip-all", "--add-gnu-debuglink=" + vmlinux_dbg, vmlinux_path, f"{self.out_dir}/vmlinux"], check=True)

        if self.arch == "arm64" and "Image" in targets:
            shutil.copy(f"{self.build_dir}/arch/{self.arch}/boot/Image", self.out_dir)
        if self.arch == "x86_64" and "bzImage" in targets:
            shutil.copy(f"{self.build_dir}/arch/{self.arch}/boot/bzImage", self.out_dir)

        if "modules" in targets:
            log.info("Copying modules to the out dir...")

            for mod in Path(self.build_dir).rglob("*.ko"):
                relative_path = str(mod).replace(str(self.build_dir), "")
                dest_dir = f"{self.out_dir}/{os.path.dirname(relative_path)}"
                os.makedirs(dest_dir, exist_ok=True)
                outmod = f"{dest_dir}/{os.path.basename(mod)}"
                subprocess.run([objcopy, "--only-keep-debug", "--compress-debug-sections", str(mod), f"{outmod}.dbg"], check=True)
                subprocess.run([objcopy, "--strip-unneeded", "--add-gnu-debuglink", f"{outmod}.dbg", str(mod), outmod], check=True)

        log.info("Moving the debug info into a separate directory...")

        for dbg in Path(self.out_dir).rglob("*.dbg"):
            relative_path = str(dbg).replace(str(self.out_dir), "")
            dest_dir = f"{self.out_dir}/DWARF/{os.path.dirname(relative_path)}"
            os.makedirs(dest_dir, exist_ok=True)
            basename = os.path.basename(dbg).replace(".dbg", ".dwarf")
            outdbg = f"{dest_dir}/{basename}"
            shutil.move(dbg, outdbg)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Builds the kernel")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging", default=False)
    parser.add_argument("-l", "--linux", type=str, help="Path to the Linux kernel source tree", default="./linux")
    parser.add_argument("-i", "--initrd", type=str, help="Initial RAM disk")
    parser.add_argument("-w", "--wipe", action="store_true", help="Do not clean before building, the default is not to wipe out the build dir", default=False)
    parser.add_argument("-r", "--redirect-stdout", action="store_true", help="Redirect the standard output to the `build*.log` files", default=False)
    parser.add_argument("-c", "--config", type=str, help="Path to the Linux kernel configuration file", required=True)
    parser.add_argument("-m", "--modules", action="store_true", help="Build kernel modules", default=False)
    parser.add_argument("arch", choices=["x86_64", "arm64"], help="Build arch")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format=log_format)

    log.debug("Arguments: %s", args)

    try:
        log.info("Preparing build environment...")

        script_dir = Path(__file__).resolve().parent
        src_dir = script_dir
        linux_src = Path(args.linux).resolve()
        if not linux_src.exists():
            raise Exception(f"Linux source directory {linux_src} does not exist")

        config_file = Path(args.config).resolve()
        if not config_file.exists():
            raise Exception(f"Config file {config_file} does not exist")

        build_dir = (src_dir / f"build/{args.config.replace('/', '-')}/{args.arch}")
        out_dir = (src_dir / f"out/{args.config.replace('/', '-')}/{args.arch}")

        if args.wipe:
            log.info("Wiping out the build and out dirs...")
            shutil.rmtree(build_dir, ignore_errors=True)
            shutil.rmtree(out_dir, ignore_errors=True)

        if not build_dir.exists():
            build_dir.mkdir(parents=True)
        build_dir = build_dir.resolve()

        if not out_dir.exists():
            out_dir.mkdir(parents=True)
        out_dir = out_dir.resolve()

        log.info("Copying the initial RAM disk")
        if args.initrd:
            shutil.copy(f"{script_dir}/{args.initrd}", f"{build_dir}/initrd-{args.arch}.cpio.gz")
        else:
            shutil.copy(f"{script_dir}/initrd-{args.arch}.cpio.gz", f"{build_dir}/initrd-{args.arch}.cpio.gz")

        os.makedirs(build_dir, exist_ok=True)
        os.makedirs(out_dir, exist_ok=True)
        os.makedirs(f"{out_dir}/modules", exist_ok=True)
        os.makedirs(f"{out_dir}/headers", exist_ok=True)

        os.chdir(linux_src)

        os.environ["KBUILD_OUTPUT"] = str(build_dir)
        os.environ["KCONFIG_CONFIG"] = str(config_file)

        log.info(f"Building {args.arch} kernel, config {config_file}...")
        builder = KernelBuilder(args.arch, linux_src, build_dir, out_dir, args.config, args.redirect_stdout, args.modules)
        builder.build_kernel()
    except Exception as e:
        if args.verbose:
            log.exception("An error occurred: %s", e)
        else:
            log.error("An error occurred: %s", e)
