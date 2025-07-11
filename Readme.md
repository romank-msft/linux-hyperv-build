# Build harness for the Linux kernel tailored to Hyper-V

Tools included produce a bootable virtual disk in the VHDX format by
using the defaults tailored to Hyper-V. The tools also have a good
set of the command line parameters for tweaking for other sceanrios.

The design goals have been to provide a way to learn easily about
constructing a working Linux-based system, be slim, iterate fast,
and read massive manuals later. A more generic system would employ
Docker or LXD, and the more generic and complex one would lean on
Yocto or Buildroot.

The purpose is to be nimbler in the developemnt and validation loop.
That said, some of this might be useful for building (small) distro's,
too. The tools were developed and tested on Ubuntu.

NOTE: This repo will not produce a system suitable for any other
purpose other than running the Linux kernel for educational purposes.
Use at your own risk.

## Preparation

### Install the dependencies

```sh
sudo apt-get update
# Toolchains:
sudo apt-get install -y gcc-x86-64-linux-gnu gcc-aarch64-linux-gnu
# To build the kernel:
sudo apt-get install -y build-essential bc flex bison libssl-dev libelf-dev
# For the `qemu-img` utility and disk partitioning
sudo apt-get install -y qemu-utils parted dosfstools

# If you'd like to play with qemu as well
sudo apt-get install -y qemu-system qemu-user-static
```

### Clone the repo

This repository uses a submodule that points to the Linux kernel source
tree. That said, here is how to clone:

```sh
git clone --recurse https://github.com/kromych/linux-hyperv-build
```

NOTE: This repo hosts few binary files for the sake of simplicity.

## An example of the whole 10 minutes flow!

This builds the VHDX images for both x64 and arm64 for specific configuration
files and all architectures:

```sh
./build-initrd.py x86_64
./build-initrd.py arm64

./build-kernel.py x86_64 -wrc config/wsl/wsl2-6.16-x64 -l linux-hyperv
./build-kernel.py arm64 -wrc config/wsl/wsl2-6.16-arm64 -l linux-hyperv

rm -f ./arm64.img ./arm64.vhdx && sudo ./build-disk-image.py arm64.img arm64 --target-image arm64.vhdx
rm -f ./x64.img ./x64.vhdx && sudo ./build-disk-image.py x64.img x86_64 --target-image x64.vhdx
sudo chown $USER:$GROUP *.img *.vhdx
```

Much more often than not, only some of that is needed. Note that omitting the `-w` parameter
when building the kernel reuses the objects from the latest build to save a lot of time.
Below are the details on how you may get more out of the provided tools.

## Buidling the kernel

```sh
usage: build-kernel.py [-h] [-v] [-l LINUX] [-i INITRD] [-w] [-r] -c CONFIG [-m] {x86_64,arm64}

Builds the kernel

positional arguments:
  {x86_64,arm64}        Build arch

options:
  -h, --help            show this help message and exit
  -v, --verbose         Enable verbose logging
  -l LINUX, --linux LINUX
                        Path to the Linux kernel source tree
  -i INITRD, --initrd INITRD
                        Initial RAM disk
  -w, --wipe            Do not clean before building, the default is not to wipe out the build dir
  -r, --redirect-stdout
                        Redirect the standard output to the `build*.log` files
  -c CONFIG, --config CONFIG
                        Path to the Linux kernel configuration file
  -m, --modules         Build kernel modules
```

This example produces a kernel with the EFI stub logging to the serial console so no
bootloader required on UEFI systems:

```sh
./build-kernel.py x86_64 -wrc config/wsl/wsl2-6.13-rc6-x64 -l linux-hyperv
```

that logs

```log
[2025-02-04 20:31:57,833][INFO    ][build-kernel] Preparing build environment...
[2025-02-04 20:31:57,833][INFO    ][build-kernel] Wiping out the build and out dirs...
[2025-02-04 20:31:58,273][INFO    ][build-kernel] Copying the initial RAM disk
[2025-02-04 20:31:58,292][INFO    ][build-kernel] Building x86_64 kernel, config /home/krom/src/linux-hyperv-build/config/wsl/wsl2-6.13-rc6-x64...
[2025-02-04 20:31:58,293][INFO    ][build-kernel] Building target vmlinux...
vmlinux.o: warning: objtool: xen_hypercall_hvm+0x38: sibling call from callable instruction with modified stack frame
[2025-02-04 20:35:24,893][INFO    ][build-kernel] Build result: 0
[2025-02-04 20:35:24,893][INFO    ][build-kernel] Building target headers_install...
[2025-02-04 20:35:25,945][INFO    ][build-kernel] Build result: 0
[2025-02-04 20:35:25,945][INFO    ][build-kernel] Building target bzImage...
[2025-02-04 20:35:32,053][INFO    ][build-kernel] Build result: 0
[2025-02-04 20:35:32,053][INFO    ][build-kernel] Stripping and compressing kernel debug info...
[2025-02-04 20:35:49,242][INFO    ][build-kernel] Moving the debug info into a separate directory...
```

The `./build` dierctory is used for building the kernel, and the `./out` directory
houses the produced kernel image, debug info, user-mode headers and modules. The debug
info is separated out into the `DWARF` subdirectory in the `./out` directory.

## Building the initial RAM disk

### `build-initrd.py`

```sh
usage: build-initrd.py [-h] [-v] [-d LAYERS_DIR] {x86_64,arm64}

Builds initramfs

positional arguments:
  {x86_64,arm64}        Initial RAM drive arch

options:
  -h, --help            show this help message and exit
  -v, --verbose         Enable verbose logging
  -d LAYERS_DIR, --layers-dir LAYERS_DIR
                        Directory with layers
```

This tool creates an initial RAM disk with various tools included. You can add
your additional layers to `./ramfs-layers`. The default one includes few
directory nodes and few device nodes, and when you run this script, another
layers will be added to the default one. The provided populated layer has been
derived from the Alpine Linux minimal root filesystem with the OpenRC initialization
system, and the layer includes various tools while staing pretty slim.

An example:

```sh
./build-initrd.py arm64
```

which gives

```log
[2025-02-04 21:36:09,869][INFO    ][build-initrd] Searching for layers in /home/krom/src/linux-hyperv-build/./ramfs-layers
[2025-02-04 21:36:09,869][INFO    ][build-initrd] Concatenating layers [PosixPath('/home/krom/src/linux-hyperv-build/ramfs-layers/000-empty-noarch.cpio.gz'), PosixPath('/home/krom/src/linux-hyperv-build/ramfs-layers/001-alpine-3.21.2-arm64.cpio.gz'), PosixPath('/home/krom/src/linux-hyperv-build/ramfs-layers/002-init-scripts-noarch.cpio.gz')] into /home/krom/src/linux-hyperv-build/initrd-arm64.cpio.gz
[2025-02-04 21:36:09,875][INFO    ][build-initrd] Adding /home/krom/src/linux-hyperv-build/ramfs-layers/000-empty-noarch.cpio.gz
[2025-02-04 21:36:09,875][INFO    ][build-initrd] Adding /home/krom/src/linux-hyperv-build/ramfs-layers/001-alpine-3.21.2-arm64.cpio.gz
[2025-02-04 21:36:09,916][INFO    ][build-initrd] Adding /home/krom/src/linux-hyperv-build/ramfs-layers/002-init-scripts-noarch.cpio.gz
```

This builds a customized initial RAM filesystem instead of the default empty one.
If you're not supplying a root filesystem, be sure to run this before building
the kernel to include a populated initial RAM filesystem.

### `gen_init_ramfs.py`

```sh
usage: gen_init_ramfs.py [-h] [--compression {gzip,bz2,lzma,none}] config_file_or_dir output_file

positional arguments:
  config_file_or_dir    Initial RAM FS configuration file or the top directory
  output_file           Output file that contains the initial RAM FS

options:
  -h, --help            show this help message and exit
  --compression {gzip,bz2,lzma,none}
                        Compression to use, default is gzip
```

This tool allows precise control via a configuration file, see `./empty-rootfs.config`
for an example.

Here is how the included empty `initrs`'s are produced:

```sh
./gen_init_ramfs.py empty-rootfs.config ./initrd-arm64.cpio.gz
./gen_init_ramfs.py empty-rootfs.config ./initrd-x86_64.cpio.gz
```

## Building the disk image

```sh
usage: build-disk-image.py [-h] [-v] [--os-loader OS_LOADER] [--disk-size DISK_SIZE] [--efi-size EFI_SIZE]
                           [--target-image TARGET_IMAGE] [--target-format {raw,qcow2,vmdk,vdi,vhdx,vpc}]
                           image_path {x86_64,arm64}

positional arguments:
  image_path            Path for the new raw disk image file (e.g. /path/to/disk.img)
  {x86_64,arm64}        Architecture of the OS loader

options:
  -h, --help            show this help message and exit
  -v, --verbose         Enable verbose logging
  --os-loader OS_LOADER
                        Path to the OS loader EFI file
  --disk-size DISK_SIZE
                        Total disk image size in MiB (default: 512)
  --efi-size EFI_SIZE   EFI partition size in MiB (default: 256)
  --target-image TARGET_IMAGE
                        Path for the converted disk image file (optional)
  --target-format {raw,qcow2,vmdk,vdi,vhdx,vpc}
```

This create a disk image with an EFI partition (FAT32) and an ext4 partition.
Optionally, converts the raw image to another disk format.

Here is an example for producing the VHDX disks:

```sh
sudo ./build-disk-image.py arm64.img arm64 --target-image arm64.vhdx
sudo ./build-disk-image.py x64.img x86_64 --target-image x64.vhdx
```

For the VHD format employed by the Gen 1 Hyper-V VMs, specify the target
format as `vpc` aka `Virtual PC` where it originates from.

Here is what the output from the above commands might look like:

```log
[2025-02-04 20:58:20,110][INFO    ][build-disk-image] Using OS loader '/home/krom/src/linux-hyperv-build/out/config-wsl-wsl2-6.13-rc6-x64/x86_64/bzImage'...
[2025-02-04 20:58:20,110][INFO    ][build-disk-image] Creating raw disk image 'x64.img' of size 512MiB...
[2025-02-04 20:58:20,113][INFO    ][build-disk-image] Attaching disk image as a loop device with partition scanning...
[2025-02-04 20:58:20,115][INFO    ][build-disk-image] Loop device /dev/loop0 created.
[2025-02-04 20:58:20,116][INFO    ][build-disk-image] Initializing /dev/loop0 with a GPT partition table...
[2025-02-04 20:58:20,145][INFO    ][build-disk-image] Creating EFI system partition from 1MiB to 257MiB...
[2025-02-04 20:58:20,323][INFO    ][build-disk-image] Creating ext4 partition from 257MiB to 100% of the disk...
[2025-02-04 20:58:22,410][INFO    ][build-disk-image] Formatting /dev/loop0p1 as FAT32 (EFI partition)...
mkfs.fat 4.2 (2021-01-31)
[2025-02-04 20:58:22,526][INFO    ][build-disk-image] Formatting /dev/loop0p2 as ext4...
mke2fs 1.47.1 (20-May-2024)
Discarding device blocks: done
Creating filesystem with 65024 4k blocks and 65024 inodes
Filesystem UUID: f9373ce3-0353-4fa8-95f8-1d3f070409cc
Superblock backups stored on blocks:
        32768

Allocating group tables: done
Writing inode tables: done
Creating journal (4096 blocks): done
Writing superblocks and filesystem accounting information: done

[2025-02-04 20:58:22,556][INFO    ][build-disk-image] Mounting /dev/loop0p1 to /tmp/efi_mount_yq112gm3...
[2025-02-04 20:58:22,563][INFO    ][build-disk-image] Creating directory /tmp/efi_mount_yq112gm3/EFI/Boot...
[2025-02-04 20:58:22,563][INFO    ][build-disk-image] Copying OS loader from '/home/krom/src/linux-hyperv-build/out/config-wsl-wsl2-6.13-rc6-x64/x86_64/bzImage' to '/tmp/efi_mount_yq112gm3/EFI/Boot/BOOTX64.EFI'...
[2025-02-04 20:58:22,752][INFO    ][build-disk-image] Unmounting /tmp/efi_mount_yq112gm3...
[2025-02-04 20:58:22,805][INFO    ][build-disk-image] Detaching loop device /dev/loop0...
[2025-02-04 20:58:22,807][INFO    ][build-disk-image] EFI boot disk image created successfully at 'x64.img'.
[2025-02-04 20:58:22,807][INFO    ][build-disk-image] Converting raw image 'x64.img' to format 'vhdx' as 'x64.vhdx'...
[2025-02-04 20:58:22,940][INFO    ][build-disk-image] Image conversion complete. Converted image is available at 'x64.vhdx'.
```

## Running with Hyper-V

Create a Generation 2 VM, disable SecureBoot, add serial ports, and point to the disk:

```powershell
$VmName = "test00-gen2"
$VhdPath = "<Full path to the vhdx from the above>"

New-Vm -VmName $VmName -Generation 2 -VHDPath $VhdPath
Set-VMFirmware -VmName $VmName -EnableSecureBoot Off
Set-VmComPort -VmName $VmName -Number 1 -Path "\\.\pipe\$VmName-com1"
Set-VmComPort -VmName $VmName -Number 2 -Path "\\.\pipe\$VmName-com2"
```

## Running with qemu

Here are few examples that can be cooked to your liking:

```sh
qemu-system-x86_64 \
  -nographic -serial mon:stdio \
  -smp 8 \
  -m 8G \
  -machine type=q35 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/qemu/OVMF.fd \
  -device virtio-scsi-pci,id=scsi0 \
  -device scsi-hd,drive=drive0,bus=scsi0.0,channel=0,scsi-id=0,lun=0 \
  -drive file=./x64.img,format=raw,if=none,id=drive0
```

```sh
qemu-system-aarch64 \
  -semihosting --semihosting-config enable=on,target=native \
  -nographic -serial mon:stdio \
  -smp 8 \
  -m 8G \
  -machine type=virt \
  -device virtio-scsi-pci,id=scsi0 \
  -device scsi-hd,drive=drive0,bus=scsi0.0,channel=0,scsi-id=0,lun=0 \
  -drive file=./arm64.img,format=raw,if=none,id=drive0
```

```sh
qemu-system-x86_64 \
  -nographic -serial mon:stdio \
  -smp 8 \
  -m 8G \
  -machine type=q35 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/qemu/OVMF.fd \
  -append "earlprintk=ttyS0,console=ttyS0 single" \
  -kernel `find ./out/ -name bzImage`
```

```sh
qemu-system-aarch64 \
  -semihosting --semihosting-config enable=on,target=native \
  -nographic -serial mon:stdio \
  -cpu cortex-a57 \
  -smp 8 \
  -m 8G \
  -machine type=virt \
  -append "earlycon,console=ttyAMA0 single" \
  -kernel `find ./out/ -name Image`
```
