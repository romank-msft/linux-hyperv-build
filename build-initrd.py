#!/usr/bin/env python3
__author__ = "romank@linux.microsoft.com"
__version__ = "0.0.1"
__license__ = "MIT"

import argparse
import logging
from pathlib import Path
import shutil

log = logging.getLogger("build-initrd")
log_format = "[%(asctime)s][%(levelname)-8s][%(name)-8s] %(message)s"

def build_initrd(layers_dir, out_file, arch):
    layers_list = []
    log.info(f"Searching for layers in {layers_dir}")
    for layer in sorted(Path(layers_dir).rglob("*.cpio.gz")):
        log.debug(f"Found layer {layer}")
        if "noarch" not in layer.name and arch not in layer.name:
            continue
        layers_list.append(layer)
    log.debug(f"Found layers {layers_list}")

    if layers_list:
        log.info(f"Concatenating layers {layers_list} into {out_file}")
        with open(out_file, "wb") as outf:
            for layer in layers_list:
                log.info(f"Adding {layer}")
                with open(layer, "rb") as inf:
                    shutil.copyfileobj(inf, outf)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Builds initramfs")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging", default=False)
    parser.add_argument("-d", "--layers-dir", help="Directory with layers", default="./ramfs-layers")
    parser.add_argument("arch", choices=["x86_64", "arm64"], help="Initial RAM drive arch")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format=log_format)

    log.debug("Arguments: %s", args)

    try:
        script_dir = Path(__file__).resolve().parent
        build_initrd(f"{script_dir}/{args.layers_dir}", f"{script_dir}/initrd-{args.arch}.cpio.gz", args.arch)
    except Exception as e:
        if args.verbose:
            log.exception("An error occurred: %s", e)
        else:
            log.error("An error occurred: %s", e)
