#!/bin/sh
# Fill in sha256sums once the v$pkgver tag exists on GitHub:
#   cd packaging/archlinux && ./update-sha256.sh
set -eu
cd "$(dirname "$0")"
. ./PKGBUILD
url="https://github.com/ElMajor76/dell-power-manager-fedora/archive/refs/tags/v${pkgver}.tar.gz"
sum="$(curl -fsSL "$url" | sha256sum | cut -d' ' -f1)"
[ "${#sum}" -eq 64 ] || { echo "could not compute checksum" >&2; exit 1; }
sed -i "s/^sha256sums=.*/sha256sums=('$sum')/" PKGBUILD
echo "sha256sums updated for $pkgver: $sum"
