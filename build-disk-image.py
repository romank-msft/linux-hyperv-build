#!/usr/bin/env python3
__author__ = "romank@linux.microsoft.com"
__version__ = "0.0.5"
__license__ = "MIT"

import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import time
import argparse
import logging

log = logging.getLogger("build-disk-image")
log_format = "[%(asctime)s][%(levelname)-8s][%(name)-8s] %(message)s"

# TODO:
#   1. Generate the kernel command line during runtime or take it from the
#      command line.
#   2. Set disk UUIDs and use "root=PARTUUID=F59E7ACA-1868-4E4D-B34D-9087DDA43174"
#   3. Add refind as the boot manager (?)
#   4. Copy the modules in if reequested

# Fixed UUIDs for partitions.
# For FAT, the volume ID is a 32-bit (8-digit hex) number.
EFI_UUID = "DEADBEEF"
# For ext4, use the standard UUID format.
EXT4_UUID = "F59E7ACA-1868-4E4D-B34D-9087DDA43174"


def create_partitions(loop_device, efi_start, efi_end_str):
    """
    Creates a GPT partition table on the loop device and creates two partitions:
    - A FAT32 EFI system partition from efi_start to efi_end_str.
    - An ext4 partition from efi_end_str to 100% of the disk.

    Returns:
        A tuple (part1, part2) representing the device paths for the EFI and ext4 partitions.
    """
    log.info("Initializing %s with a GPT partition table...", loop_device)
    subprocess.run(["parted", "-s", loop_device, "mklabel", "gpt"], check=True)

    log.info("Creating EFI system partition from %s to %s...", efi_start, efi_end_str)
    subprocess.run(
        ["parted", "-s", loop_device, "mkpart", "primary", "fat32", efi_start, efi_end_str],
        check=True
    )
    subprocess.run(["parted", "-s", loop_device, "set", "1", "boot", "on"], check=True)
    subprocess.run(["parted", "-s", loop_device, "set", "1", "esp", "on"], check=True)

    log.info("Creating ext4 partition from %s to 100%% of the disk...", efi_end_str)
    subprocess.run(
        ["parted", "-s", loop_device, "mkpart", "primary", "ext4", efi_end_str, "100%"],
        check=True
    )

    time.sleep(2)

    part1 = f"{loop_device}p1"
    part2 = f"{loop_device}p2"

    if not os.path.exists(part1):
        raise RuntimeError(f"Expected partition device {part1} does not exist.")
    if not os.path.exists(part2):
        raise RuntimeError(f"Expected partition device {part2} does not exist.")

    return part1, part2


def fill_boot_partition(part1, os_loader, arch):
    """
    Mounts the EFI (boot) partition, creates the EFI/Boot directory, and copies
    the OS loader file to the appropriate location based on the architecture.
    """
    efi_mount_dir = tempfile.mkdtemp(prefix="efi_mount_")
    log.info("Mounting boot partition %s to %s...", part1, efi_mount_dir)
    subprocess.run(["mount", part1, efi_mount_dir], check=True)
    try:
        boot_dir = os.path.join(efi_mount_dir, "EFI", "Boot")
        log.info("Creating boot directory %s...", boot_dir)
        os.makedirs(boot_dir, exist_ok=True)

        if arch == "x86_64":
            efi_file = "BOOTX64.EFI"
        elif arch == "arm64":
            efi_file = "BOOTAA64.EFI"
        else:
            raise ValueError(f"Unsupported architecture: {arch}")

        dest_loader = os.path.join(boot_dir, efi_file)
        log.info("Copying OS loader from '%s' to '%s'...", os_loader, dest_loader)
        shutil.copy2(os_loader, dest_loader)
    finally:
        log.info("Unmounting boot partition from %s...", efi_mount_dir)
        subprocess.run(["umount", efi_mount_dir], check=True)
        os.rmdir(efi_mount_dir)


def fill_ext4_partition(part2, arch):
    """
    Mounts the ext4 partition and extracts cpio.gz layers from the 'virtdisk-layers' directory.
    Only layers that are marked as "noarch" or match the specified architecture are processed.
    """
    root_mount_dir = tempfile.mkdtemp(prefix="root_mount_")
    log.info("Mounting ext4 partition %s to %s...", part2, root_mount_dir)
    subprocess.run(["mount", part2, root_mount_dir], check=True)
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        layers_dir = os.path.join(script_dir, "virtdisk-layers")
        if os.path.exists(layers_dir):
            found = False
            for layer in sorted(Path(layers_dir).rglob("*.cpio.gz")):
                log.debug(f"Found layer {layer}")
                if "noarch" not in layer.name and arch not in layer.name:
                    log.debug(f"Skipping {layer} (does not match arch {arch})")
                    continue
                found = True
                log.info("Extracting '%s' into ext4 partition at '%s'...", layer, root_mount_dir)
                subprocess.run(f"gunzip -c {layer} | cpio -idm", shell=True, cwd=root_mount_dir, check=True)
            if not found:
                log.info("No appropriate cpio.gz files found in '%s'", layers_dir)
        else:
            log.warning("Directory '%s' does not exist, skipping layer extraction", layers_dir)
    finally:
        log.info("Unmounting ext4 partition from %s...", root_mount_dir)
        subprocess.run(["umount", root_mount_dir], check=True)
        os.rmdir(root_mount_dir)


def new_efi_boot_disk(image_path, os_loader, arch, disk_size_mib=512, efi_size_mib=256,
                        target_image=None, target_format=None):
    if disk_size_mib <= efi_size_mib + 1:
        raise ValueError("Disk size must be greater than EFI size plus 1 MiB for proper partition alignment.")

    if os.path.exists(image_path):
        raise FileExistsError(f"Disk image at {image_path} already exists.")

    disk_size_str = f"{disk_size_mib}MiB"
    efi_start = "1MiB"
    efi_end_mib = 1 + efi_size_mib
    efi_end_str = f"{efi_end_mib}MiB"

    log.info("Creating raw disk image '%s' of size %s...", image_path, disk_size_str)
    try:
        subprocess.run(["fallocate", "-l", disk_size_str, image_path], check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to create disk image: {e}")

    log.info("Attaching disk image as a loop device with partition scanning...")
    try:
        result = subprocess.run(
            ["losetup", "--find", "--partscan", "--show", image_path],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        loop_device = result.stdout.strip()
        log.info("Loop device %s created.", loop_device)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to set up loop device: {e}")

    try:
        # Create partitions on the loop device.
        part1, part2 = create_partitions(loop_device, efi_start, efi_end_str)

        log.info("Formatting boot partition %s as FAT32 with fixed UUID %s...", part1, EFI_UUID)
        subprocess.run(["mkfs.fat", "-F32", "-n", "EFI", "-i", EFI_UUID, part1], check=True)

        log.info("Formatting ext4 partition %s...", part2)
        subprocess.run(["mkfs.ext4", "-F", "-L", "ROOT", part2], check=True)
        log.info("Setting fixed UUID on ext4 partition %s to %s...", part2, EXT4_UUID)
        subprocess.run(["tune2fs", "-U", EXT4_UUID, part2], check=True)

        # Fill the boot partition.
        fill_boot_partition(part1, os_loader, arch)

        # Fill the ext4 partition.
        fill_ext4_partition(part2, arch)

    finally:
        log.info("Detaching loop device %s...", loop_device)
        subprocess.run(["losetup", "-d", loop_device], check=True)

    log.info("EFI boot disk image created successfully at '%s'.", image_path)

    if target_image and target_format:
        log.info("Converting raw image '%s' to format '%s' as '%s'...",
                 image_path, target_format, target_image)
        try:
            subprocess.run(
                ["qemu-img", "convert", "-O", target_format, image_path, target_image],
                check=True
            )
            log.info("Image conversion complete. Converted image is available at '%s'.", target_image)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Image conversion failed: {e}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Create a disk image with an EFI partition (FAT32) and an ext4 partition. "
                    "Optionally, convert the raw image to another disk format."
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging", default=False)
    parser.add_argument("image_path", help="Path for the new raw disk image file (e.g. /path/to/disk.img)")
    parser.add_argument("arch", choices=["x86_64", "arm64"], help="Architecture of the OS loader")
    parser.add_argument("--os-loader", help="Path to the OS loader EFI file", required=False)
    parser.add_argument("--disk-size", type=int, default=512,
                        help="Total disk image size in MiB (default: 512)")
    parser.add_argument("--efi-size", type=int, default=256,
                        help="EFI partition size in MiB (default: 256)")
    parser.add_argument("--target-image", help="Path for the converted disk image file (optional)")
    parser.add_argument("--target-format",
                        choices=["raw", "qcow2", "vmdk", "vdi", "vhdx", "vpc"],
                        default="vhdx",
                        help="Target disk format for conversion (allowed choices: raw, qcow2, vmdk, vdi, vhdx, vpc)")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format=log_format)

    log.debug("Arguments: %s", args)

    script_dir = Path(__file__).resolve().parent

    def get_os_loaders():
        os_loaders = []
        if args.arch == "x86_64":
            os_loader = "bzImage"
        elif args.arch == "arm64":
            os_loader = "Image"
        else:
            raise ValueError(f"Unsupported architecture: {args.arch}")
        for root, _, files in os.walk(f"{script_dir}/out"):
            if os_loader in files:
                os_loader = os.path.join(root, os_loader)
                os_loaders.append(os_loader)
        return os_loaders

    try:
        if not args.os_loader:
            os_loaders = get_os_loaders()
            if not os_loaders:
                raise FileNotFoundError(f"OS loader not found for architecture {args.arch}, make sure to build the kernel first")
            elif len(os_loaders) > 1:
                raise FileExistsError(f"Multiple OS loaders found for architecture {args.arch}: {os_loaders}, please specify the one to use with --os-loader")
            else:
                log.info("Using OS loader '%s'...", os_loaders[0])
                args.os_loader = os_loaders[0]

        new_efi_boot_disk(
            args.image_path,
            args.os_loader,
            args.arch,
            disk_size_mib=args.disk_size,
            efi_size_mib=args.efi_size,
            target_image=args.target_image,
            target_format=args.target_format
        )
    except Exception as e:
        if args.verbose:
            log.exception("An error occurred: %s", e)
        else:
            log.error("An error occurred: %s", e)
