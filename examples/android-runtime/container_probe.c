/* Original VegaBridge container prerequisite probe.
 * Child-only namespace trials; no mounts, service registration, privilege
 * changes, device transactions, Android installation or APK execution.
 * Define VB_APP_LIBRARY to run via a normal app's native autolink entry point.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sys/types.h>
#include <linux/android/binder.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

struct trial { int result, error, signal; };

/* A successful namespace exists only in this disposable child. */
static struct trial namespace_trial(int flags) {
    int channel[2], status = 0;
    struct trial value = {-1, 0, 0};
    if (pipe(channel) != 0) { value.error = errno; return value; }
    pid_t child = fork();
    if (child < 0) { value.error = errno; close(channel[0]); close(channel[1]); return value; }
    if (child == 0) {
        close(channel[0]);
        alarm(3);
        value.result = unshare(flags);
        value.error = value.result < 0 ? errno : 0;
        ssize_t ignored = write(channel[1], &value, sizeof(value));
        (void)ignored;
        _exit(0);
    }
    close(channel[1]);
    ssize_t bytes = read(channel[0], &value, sizeof(value));
    close(channel[0]);
    while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
    if (WIFSIGNALED(status)) value.signal = WTERMSIG(status);
    if (bytes != sizeof(value)) { value.result = -1; value.error = EIO; }
    return value;
}

static int listed(const char *file, const char *needle) {
    char line[512];
    FILE *in = fopen(file, "r");
    if (!in) return -errno;
    int found = 0;
    while (fgets(line, sizeof(line), in)) if (strstr(line, needle)) { found = 1; break; }
    fclose(in);
    return found;
}

static void context(FILE *out) {
    const char *keys[] = {"CapEff:", "CapBnd:", "NoNewPrivs:", "Seccomp:"};
    const char *names[] = {"capEff", "capBnd", "noNewPrivs", "seccomp"};
    char line[512];
    FILE *in = fopen("/proc/self/status", "r");
    fprintf(out, "\"context\":{\"pid\":%ld,\"uid\":%lu,\"gid\":%lu,\"userspaceBits\":%zu",
            (long)getpid(), (unsigned long)getuid(), (unsigned long)getgid(), sizeof(void *) * 8);
    if (in) {
        while (fgets(line, sizeof(line), in)) {
            for (size_t i = 0; i < 4; ++i) if (!strncmp(line, keys[i], strlen(keys[i]))) {
                char value[80] = {0};
                if (sscanf(line + strlen(keys[i]), "%79s", value) == 1)
                    fprintf(out, ",\"%s\":\"%s\"", names[i], value);
            }
        }
        fclose(in);
    }
    fprintf(out, "}");
}

static void report(FILE *out) {
    int fd = open("/dev/binder", O_RDONLY | O_CLOEXEC), binder_error = fd < 0 ? errno : 0;
    int result = -1, query_error = 0;
    struct binder_version version = {0};
    if (fd >= 0) { result = ioctl(fd, BINDER_VERSION, &version); query_error = result < 0 ? errno : 0; close(fd); }
    int mem = memfd_create("vegabridge-container-query", MFD_CLOEXEC);
    int mem_error = mem < 0 ? errno : 0, mem_rw = 0;
    if (mem >= 0) {
        char value[4] = {0};
        mem_rw = write(mem, "VBQ", 3) == 3 && lseek(mem, 0, SEEK_SET) == 0 && read(mem, value, 3) == 3 && !memcmp(value, "VBQ", 3);
        close(mem);
    }
    fprintf(out, "{\"schemaVersion\":1,");
    context(out);
    fprintf(out, ",\"binder\":{\"openErrno\":%d,\"versionQueryResult\":%d,\"queryErrno\":%d,\"protocol\":%d},"
            "\"binderfsListed\":%d,\"memfd\":{\"openErrno\":%d,\"readWritePassed\":%s},\"namespaces\":{",
            binder_error, result, query_error, version.protocol_version, listed("/proc/filesystems", "binder"), mem_error, mem_rw ? "true" : "false");
    const char *names[] = {"user", "mount", "userMount", "userIpc", "userPid", "userNet", "userUts"};
    const int flags[] = {CLONE_NEWUSER, CLONE_NEWNS, CLONE_NEWUSER | CLONE_NEWNS, CLONE_NEWUSER | CLONE_NEWIPC,
                        CLONE_NEWUSER | CLONE_NEWPID, CLONE_NEWUSER | CLONE_NEWNET, CLONE_NEWUSER | CLONE_NEWUTS};
    for (size_t i = 0; i < sizeof(flags) / sizeof(flags[0]); ++i) {
        struct trial value = namespace_trial(flags[i]);
        fprintf(out, "%s\"%s\":{\"result\":%d,\"errno\":%d,\"signal\":%d}", i ? "," : "", names[i], value.result, value.error, value.signal);
    }
    fprintf(out, "},\"hostNamespaceChanged\":false,\"mountAttempted\":false,\"binderTransactionAttempted\":false,"
            "\"androidRuntimeBooted\":false,\"apkExecuted\":false}\n");
    fflush(out);
}

#ifdef VB_APP_LIBRARY
__attribute__((visibility("default"))) void autoLinkKeplerTurboModulesV1(void) {
    int fd = open("/scratch/container-capabilities.json", O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) return;
    FILE *out = fdopen(fd, "w");
    if (!out) { close(fd); return; }
    report(out);
    fclose(out);
}
__attribute__((constructor)) static void probe_on_load(void) {
    autoLinkKeplerTurboModulesV1();
}
#else
int main(void) { report(stdout); return ferror(stdout) ? 1 : 0; }
#endif
