#!/usr/bin/env bash
# ConfClean FC - RPM Packaging Script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PKG_NAME="confclean-fc"
PKG_VERSION="${PKG_VERSION:-$(PYTHONPATH="${ROOT_DIR}" python3 -c "import confclean; print(confclean.__version__)")}"
RPMBUILD_DIR="${ROOT_DIR}/rpmbuild"
DIST_TAG="${DIST_TAG:-%{nil}}"

# Locate rpmbuild binary or standalone runner
if command -v rpmbuild >/dev/null 2>&1; then
    RPMBUILD_BIN="$(command -v rpmbuild)"
elif [ -x "/tmp/rpmbuild_tool/usr/bin/rpmbuild" ]; then
    RPMBUILD_BIN="/tmp/rpmbuild_tool/usr/bin/rpmbuild"
elif [ -x "/tmp/usr/bin/rpmbuild" ]; then
    RPMBUILD_BIN="/tmp/usr/bin/rpmbuild"
else
    RUNNER_BIN="${SCRIPT_DIR}/rpmbuild-runner"
    if [ ! -x "${RUNNER_BIN}" ]; then
        echo "==> Compiling native librpmbuild runner..."
        gcc -O2 -o "${RUNNER_BIN}" "${SCRIPT_DIR}/rpmbuild-runner.c" -lrpm -lrpmbuild -lrpmio
    fi
    RPMBUILD_BIN="${RUNNER_BIN}"
fi

RPMUNCOMPRESS_BIN="$(command -v rpmuncompress || (test -x /tmp/rpmbuild_tool/usr/bin/rpmuncompress && echo /tmp/rpmbuild_tool/usr/bin/rpmuncompress) || (test -x /tmp/usr/bin/rpmuncompress && echo /tmp/usr/bin/rpmuncompress) || echo "/bin/tar -x -f")"

echo "==> Using rpmbuild: ${RPMBUILD_BIN}"
echo "==> Preparing build environment for ${PKG_NAME}-${PKG_VERSION}..."

rm -rf "${RPMBUILD_DIR}"
mkdir -p "${RPMBUILD_DIR}"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

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

echo "==> Building binary and source RPM packages (dist tag: '${DIST_TAG}')..."
"${RPMBUILD_BIN}" \
    --define "_topdir ${RPMBUILD_DIR}" \
    --define "_tmppath /tmp" \
    --define "dist ${DIST_TAG}" \
    --define "__rpmuncompress ${RPMUNCOMPRESS_BIN}" \
    -ba "${RPMBUILD_DIR}/SPECS/confclean-fc.spec"

# Find generated RPMs
RPM_FILE="$(find "${RPMBUILD_DIR}/RPMS" -name "*.rpm" | head -n 1)"
SRPM_FILE="$(find "${RPMBUILD_DIR}/SRPMS" -name "*.src.rpm" | head -n 1)"

if [ -z "${RPM_FILE}" ] || [ ! -f "${RPM_FILE}" ]; then
    echo "Error: RPM build failed to produce a binary rpm package." >&2
    exit 1
fi

RPM_FILENAME="$(basename "${RPM_FILE}")"

# Purge any older RPMs in dist and root to ensure only the latest unified RPMs exist
find "${ROOT_DIR}" -maxdepth 1 -name "confclean-fc-*.noarch.rpm" ! -name "${RPM_FILENAME}" -delete 2>/dev/null || true

cp "${RPM_FILE}" "${ROOT_DIR}/${RPM_FILENAME}"

SRPM_FILENAME=""
if [ -n "${SRPM_FILE}" ] && [ -f "${SRPM_FILE}" ]; then
    SRPM_FILENAME="$(basename "${SRPM_FILE}")"
    find "${ROOT_DIR}" -maxdepth 1 -name "confclean-fc-*.src.rpm" ! -name "${SRPM_FILENAME}" -delete 2>/dev/null || true
        cp "${SRPM_FILE}" "${ROOT_DIR}/${SRPM_FILENAME}"
fi

# Generate SHA256 checksums
echo "==> Generating SHA256SUMS..."
cd "${ROOT_DIR}"
if [ -n "${SRPM_FILENAME}" ]; then
    sha256sum "${RPM_FILENAME}" "${SRPM_FILENAME}" > "${ROOT_DIR}/SHA256SUMS"
else
    sha256sum "${RPM_FILENAME}" > "${ROOT_DIR}/SHA256SUMS"
fi

# Clean up build tree intermediates so only the current release artifacts are retained
rm -rf "${RPMBUILD_DIR}"

echo ""
echo "============================================================"
echo "  RPM BUILD SUCCESSFUL!"
echo "  Binary Package: ${ROOT_DIR}/${RPM_FILENAME}"
if [ -n "${SRPM_FILENAME}" ]; then
    echo "  Source Package: ${ROOT_DIR}/${SRPM_FILENAME}"
fi
echo "============================================================"
echo ""
echo "To install binary package on your system:"
echo "  sudo dnf install ./${RPM_FILENAME}"
echo "  # or:"
echo "  sudo rpm -ivh ./${RPM_FILENAME}"
if [ -n "${SRPM_FILENAME}" ]; then
    echo ""
    echo "To rebuild from source RPM:"
    echo "  rpmbuild --rebuild ./${SRPM_FILENAME}"
fi
echo ""
echo "Package Details:"
rpm -qip "${ROOT_DIR}/${RPM_FILENAME}"
echo ""
echo "Package File List:"
rpm -qlp "${ROOT_DIR}/${RPM_FILENAME}"
