# ConfClean FC - Workspace Rules

## Mandatory Rules (No Exceptions)

1. **Version Number Incrementation**:
   - You **MUST** increment the version / release number each time any change is made to the codebase.
   - Update `packaging/confclean-fc.spec` (`Release: <N>%{?dist}` and `%changelog`).
   - Synchronize all references in `docs/INSTALLATION.md` and `README.md`.

2. **RPM Regeneration**:
   - You **MUST** regenerate both the binary (`.noarch.rpm`) and source (`.src.rpm`) RPM packages via `bash packaging/build-rpm.sh` to match the newest changes.
   - Update `SHA256SUMS` to reflect the newly built packages.
   - Clean up any older RPM packages from the repository root.

3. **Verification**:
   - Run the automated test suite (`python3 -m unittest discover tests`) before committing to ensure all tests pass.
