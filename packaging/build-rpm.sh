#!/usr/bin/env bash
# ConfClean FC - RPM Packaging Script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PKG_NAME="confclean-fc"
PKG_VERSION="${PKG_VERSION:-$(PYTHONPATH="${ROOT_DIR}" python3 -c "import confclean; print(confclean.__version__)")}"
DIST_DIR="${ROOT_DIR}/dist"
RPMBUILD_DIR="${ROOT_DIR}/rpmbuild"
DIST_TAG="${DIST_TAG:-%{nil}}"

# Locate rpmbuild binary
if command -v rpmbuild >/dev/null 2>&1; then
    RPMBUILD_BIN="$(command -v rpmbuild)"
elif [ -x "/tmp/rpmbuild_tool/usr/bin/rpmbuild" ]; then
    RPMBUILD_BIN="/tmp/rpmbuild_tool/usr/bin/rpmbuild"
    export LD_LIBRARY_PATH="/tmp/rpmbuild_tool/usr/lib64:${LD_LIBRARY_PATH}"
else
    echo "Error: rpmbuild binary not found. Please install rpm-build (sudo dnf install rpm-build)." >&2
    exit 1
fi

echo "==> Using rpmbuild: ${RPMBUILD_BIN}"
echo "==> Preparing build environment for ${PKG_NAME}-${PKG_VERSION}..."

rm -rf "${RPMBUILD_DIR}"
mkdir -p "${RPMBUILD_DIR}"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
mkdir -p "${DIST_DIR}"

# Prepare source archive
TMP_SRC="/tmp/${PKG_NAME}-${PKG_VERSION}"
rm -rf "${TMP_SRC}"
mkdir -p "${TMP_SRC}"

cp -r "${ROOT_DIR}/confclean" "${TMP_SRC}/"
cp -r "${ROOT_DIR}/assets" "${TMP_SRC}/"
cp -r "${ROOT_DIR}/docs" "${TMP_SRC}/"
cp -r "${ROOT_DIR}/packaging" "${TMP_SRC}/"
cp "${ROOT_DIR}/main.py" "${TMP_SRC}/"
cp "${ROOT_DIR}/README.md" "${TMP_SRC}/"
cp "${ROOT_DIR}/CONTRIBUTING.md" "${TMP_SRC}/"
cp "${ROOT_DIR}/LICENSE" "${TMP_SRC}/"
cp "${ROOT_DIR}/requirements.txt" "${TMP_SRC}/"
cp "${ROOT_DIR}/pyproject.toml" "${TMP_SRC}/"

# Clean any pycache in source archive
find "${TMP_SRC}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${TMP_SRC}" -name "*.pyc" -delete 2>/dev/null || true

# Touch all source files to set current timestamp so RPM unpack never leaves source older than previous runtimes
find "${TMP_SRC}" -exec touch {} +

echo "==> Creating source tarball: ${RPMBUILD_DIR}/SOURCES/${PKG_NAME}-${PKG_VERSION}.tar.gz..."
tar -czf "${RPMBUILD_DIR}/SOURCES/${PKG_NAME}-${PKG_VERSION}.tar.gz" -C /tmp "${PKG_NAME}-${PKG_VERSION}"
rm -rf "${TMP_SRC}"

# Copy spec file
cp "${SCRIPT_DIR}/confclean-fc.spec" "${RPMBUILD_DIR}/SPECS/"

echo "==> Building binary RPM package (dist tag: '${DIST_TAG}')..."
"${RPMBUILD_BIN}" \
    --define "_topdir ${RPMBUILD_DIR}" \
    --define "_tmppath /tmp" \
    --define "dist ${DIST_TAG}" \
    -bb "${RPMBUILD_DIR}/SPECS/confclean-fc.spec"

# Find generated RPM
RPM_FILE="$(find "${RPMBUILD_DIR}/RPMS" -name "*.rpm" | head -n 1)"

if [ -z "${RPM_FILE}" ] || [ ! -f "${RPM_FILE}" ]; then
    echo "Error: RPM build failed to produce an rpm package." >&2
    exit 1
fi

RPM_FILENAME="$(basename "${RPM_FILE}")"
cp "${RPM_FILE}" "${DIST_DIR}/${RPM_FILENAME}"
cp "${RPM_FILE}" "${ROOT_DIR}/${RPM_FILENAME}"

echo ""
echo "============================================================"
echo "  RPM BUILD SUCCESSFUL!"
echo "  Package: ${ROOT_DIR}/${RPM_FILENAME}"
echo "============================================================"
echo ""
echo "To install manually on your system:"
echo "  sudo dnf install ./${RPM_FILENAME}"
echo "  # or:"
echo "  sudo rpm -ivh ./${RPM_FILENAME}"
echo ""
echo "Package Details:"
rpm -qip "${ROOT_DIR}/${RPM_FILENAME}"
echo ""
echo "Package File List:"
rpm -qlp "${ROOT_DIR}/${RPM_FILENAME}"
