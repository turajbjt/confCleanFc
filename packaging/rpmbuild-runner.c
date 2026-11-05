/*
 * ConfClean FC - Standalone RPM Build Runner
 * Uses librpm, librpmbuild, and librpmio directly to build binary and source RPMs
 * when the rpmbuild command-line tool is not installed or when running in restricted environments.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <rpm/rpmlib.h>
#include <rpm/rpmbuild.h>
#include <rpm/rpmts.h>
#include <rpm/rpmmacro.h>

static void ensure_rpmuncompress(void) {
    if (access("/usr/bin/rpmuncompress", X_OK) == 0) {
        return;
    }
    const char *helper = "/tmp/rpmuncompress_helper";
    FILE *f = fopen(helper, "w");
    if (f) {
        fprintf(f, "#!/bin/bash\n"
                   "if [ \"$1\" = \"-x\" ]; then\n"
                   "    shift\n"
                   "fi\n"
                   "exec tar -xf \"$@\"\n");
        fclose(f);
        chmod(helper, 0755);
        char macro[512];
        snprintf(macro, sizeof(macro), "__rpmuncompress %s", helper);
        rpmDefineMacro(NULL, macro, 0);
    }
}

int main(int argc, char *argv[]) {
    // 1. Initialize RPM configuration and load macro files first
    if (rpmReadConfigFiles(NULL, NULL)) {
        fprintf(stderr, "Error: rpmReadConfigFiles failed\n");
        return 1;
    }

    // 2. Set safe defaults for sandbox / container builds
    rpmDefineMacro(NULL, "_tmppath /tmp", 0);
    rpmDefineMacro(NULL, "dist %{nil}", 0);
    rpmDefineMacro(NULL, "__check_files %{nil}", 0);
    rpmDefineMacro(NULL, "_unpackaged_files_terminate_build 0", 0);

    const char *specfile = NULL;
    const char *topdir = NULL;
    int build_source = 0;
    int build_binary = 1;

    // 3. Process command line arguments and user defines (overrides defaults)
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-ba") == 0) {
            build_source = 1;
            build_binary = 1;
        } else if (strcmp(argv[i], "-bb") == 0) {
            build_source = 0;
            build_binary = 1;
        } else if (strcmp(argv[i], "-bs") == 0) {
            build_source = 1;
            build_binary = 0;
        } else if (strcmp(argv[i], "--define") == 0 && i + 1 < argc) {
            i++;
            rpmDefineMacro(NULL, argv[i], 0);
        } else if (strncmp(argv[i], "--define=", 9) == 0) {
            rpmDefineMacro(NULL, argv[i] + 9, 0);
        } else if (strcmp(argv[i], "--topdir") == 0 && i + 1 < argc) {
            topdir = argv[++i];
        } else if (argv[i][0] != '-') {
            specfile = argv[i];
        }
    }

    if (topdir) {
        char buf[1024];
        snprintf(buf, sizeof(buf), "_topdir %s", topdir);
        rpmDefineMacro(NULL, buf, 0);
    }

    if (!specfile) {
        fprintf(stderr, "Usage: %s [-ba|-bb|-bs] [--define \"macro value\"] <specfile> [topdir]\n", argv[0]);
        return 1;
    }

    ensure_rpmuncompress();

    rpmts ts = rpmtsCreate();
    rpmSpec spec = rpmSpecParse(specfile, RPMSPEC_NOFINALIZE, NULL);
    if (!spec) {
        fprintf(stderr, "Error: Failed to parse spec file: %s\n", specfile);
        rpmtsFree(ts);
        rpmFreeRpmrc();
        return 1;
    }

    struct rpmBuildArguments_s ba;
    memset(&ba, 0, sizeof(ba));
    ba.buildAmount = RPMBUILD_MKBUILDDIR | RPMBUILD_PREP | RPMBUILD_BUILD | RPMBUILD_INSTALL | RPMBUILD_CLEAN;
    if (build_binary) {
        ba.buildAmount |= RPMBUILD_PACKAGEBINARY;
    }
    if (build_source) {
        ba.buildAmount |= RPMBUILD_PACKAGESOURCE;
    }

    printf("==> Running rpmSpecBuild for %s...\n", specfile);
    int rc = rpmSpecBuild(ts, spec, &ba);

    rpmSpecFree(spec);
    rpmtsFree(ts);
    rpmFreeRpmrc();

    if (rc != 0) {
        fprintf(stderr, "Error: rpmSpecBuild returned code %d\n", rc);
    }
    return rc;
}
