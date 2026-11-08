/* Original VegaBridge research probe. Uses external Linux UAPI headers.
 * Queries driver versions only: no Binder transactions, service registration,
 * VM creation, device configuration or permission changes.
 */
#include <errno.h>
#include <fcntl.h>
#include <sys/types.h>
#include <linux/android/binder.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>

static void binder_query(void) {
    int fd = open("/dev/binder", O_RDONLY | O_CLOEXEC);
    int open_error = fd < 0 ? errno : 0;
    int is_character = 0, result = -1, query_error = 0;
    struct binder_version version = {0};
    if (fd >= 0) {
        struct stat info;
        if (fstat(fd, &info) == 0) is_character = S_ISCHR(info.st_mode) ? 1 : 0;
        if (is_character) { result = ioctl(fd, BINDER_VERSION, &version); query_error = result < 0 ? errno : 0; }
        close(fd);
    }
    printf("\"binder\":{\"openErrno\":%d,\"characterDevice\":%d,\"versionQueryResult\":%d,\"queryErrno\":%d,\"protocol\":%d}",
           open_error, is_character, result, query_error, version.protocol_version);
}

static void kvm_query(void) {
    int fd = open("/dev/kvm", O_RDONLY | O_CLOEXEC);
    int open_error = fd < 0 ? errno : 0, version = -1, query_error = 0;
    if (fd >= 0) {
        version = ioctl(fd, _IO(0xAE, 0), 0); /* KVM_GET_API_VERSION; does not create a VM. */
        query_error = version < 0 ? errno : 0;
        close(fd);
    }
    printf("\"kvm\":{\"openErrno\":%d,\"apiVersion\":%d,\"queryErrno\":%d}",open_error,version,query_error);
}

int main(void) {
    printf("{\"userspaceBits\":%zu,\"uid\":%lu,",sizeof(void *) * 8,(unsigned long)getuid());
    binder_query();printf(",");kvm_query();
    printf(",\"apkExecuted\":false,\"androidRuntimeBooted\":false}\n");
    return 0;
}
