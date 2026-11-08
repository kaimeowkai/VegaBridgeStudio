# Android compatibility runtime research

The target is a reusable runtime package for unchanged APKs alongside shared conversion tooling. The released workbench contains assessment/planning tools and prerequisite observations. It does not include an Android runtime or claim APK execution or broad application compatibility. A private software-guest experiment reached Android framework boot, but did not pass an unchanged app's UI launch.

## Architecture choices

| Route | Shared implementation needed | Current status |
| --- | --- | --- |
| Automated conversion | Versioned Android API mappings, common Vega adapters, translation and behavior-equivalence tests | Assessment and adapter-plan GUI implemented; converter/adapter implementations remain future work |
| Android container | Android userspace/runtime/services plus suitable kernel interfaces, isolation and display/input/audio integration | Prerequisite observations and one driver query completed; no Android container booted |
| Full Android guest | Emulator, compatible Android guest, display/input/audio bridge and resource controls | Private software experiment reached framework boot and APK installation; app UI execution failed qualification; no runtime is included |
| Userspace compatibility layer | Android framework semantics, runtime, ABI and system-service mediation | Research architecture only |

Android's app environment includes ART, framework APIs, native libraries and system services above the kernel. A reusable package would have to supply or emulate the required environment. [AOSP architecture](https://source.android.com/docs/core/architecture).

Waydroid demonstrates the container approach using a complete Android system and Linux namespaces. Its documentation calls for Binder and ashmem or memfd support. It is a reference architecture, not a drop-in Vega package or a bundled dependency here. [Waydroid overview](https://docs.waydro.id/), [kernel requirements](https://docs.waydro.id/debugging/getting-essential-information).

QEMU offers system emulation through accelerators or software TCG. Lack of a visible KVM device does not rule out software emulation, but software performance and guest integration would require an actual test. [QEMU architecture](https://www.qemu.org/docs/master/system/introduction.html).

## Actual emulator findings

In the existing x86_64 Vega VM, the developer shell exposed `/dev/binder` and a GPU render node. `/dev/kvm` was not exposed. The checked optional developer component context was unavailable; no claim about production app privileges is made.

The original [native capability probe](../examples/android-runtime/capability_probe.c) was built with Windows LLVM against the external SDK sysroots for ARMv7, AArch64 and x86_64. Only the x86_64 binary was executed, in the emulator's developer shell:

- The process had UID 5000 and a 64-bit userspace.
- `/dev/binder` opened as a character device. Its `BINDER_VERSION` query succeeded and returned protocol 8.
- Opening `/dev/kvm` returned ENOENT in that context.
- The probe made no Binder transactions, registered no service, created no VM and changed no device permissions. Its temporary executable was removed after the query.

The Binder version operation is a Linux/Android UAPI query. The sample includes the user's external system header rather than distributing the SDK header. [UAPI reference](https://android.googlesource.com/kernel/common/+/d04d0acdaf98506fca2e6501ed6adcdcc7d31a1f/include/uapi/linux/android/binder.h).

Binder success is a useful prerequisite result. It does not show that a private Android service environment, ART, framework resources, graphics, Google services, media or device-specific APIs work. Using the system's existing Binder context for a private Android runtime has not been demonstrated; this probe does not change that context.

The physical Fire TV Stick 4K Select is a different target. Amazon lists a 32-bit application ABI and 1 GB of RAM; the development VM used about 4 GB of assigned RAM. No physical-device runtime test was performed, and emulator resources must not be treated as device resources. [Device specifications](https://developer.amazon.com/docs/fire-tv/device-specifications-fire-tv-streaming-media-player.html).

## Next research gates

1. Qualify the same minimal driver query from an ordinary Vega application component, without relying on developer-shell privileges.
2. Establish an isolated Android service namespace or an alternative IPC mediation design without interfering with Vega services.
3. Bring up a minimal ART/framework environment and run one unchanged, original test APK with UI and remote input. Record actual API coverage and memory/CPU use.
4. Test the same runtime against several unrelated app shapes. Track missing APIs centrally; do not fix only a single app and call the runtime general.
5. Measure startup, memory, graphics/input and lifecycle under realistic device limits before considering larger apps or publication.

All-Android-app support is an aspiration, not a current capability or a guarantee. The next milestone is one unchanged APK running inside a demonstrably reusable runtime.

## Container feasibility investigation — November 8, 2026

The existing x86_64 Vega virtual-device image exposes kernel release `6.1.57-yocto-standard`. Its readable running-kernel configuration and bounded native trials produced the following results:

| Prerequisite | Actual result in this image |
| --- | --- |
| Android Binder IPC | Enabled; read-only version query returned protocol 8 |
| Anonymous memory files | `CONFIG_MEMFD_CREATE=y`; create/write/read/close passed |
| User namespaces | `CONFIG_USER_NS=y`, limit 15632, but `unshare(CLONE_NEWUSER)` returned EPERM |
| Mount namespace | `unshare(CLONE_NEWNS)` returned EPERM |
| User plus mount/IPC/PID/network/UTS namespaces | Each separate disposable-child trial returned EPERM |
| Private Binder filesystem | `CONFIG_ANDROID_BINDERFS` is explicitly not set; no binder filesystem listed |
| KVM | `CONFIG_KVM` is explicitly not set in this virtual-device kernel |

The same native trials ran in a developer shell and a developer-invoked shell inside a separately installed QA app namespace. Both had zero effective and bounding capabilities, `NoNewPrivs=1`, and `Seccomp=0`. These are **developer-shell results**, not native execution in the normal app process.

A read-only status observation of the ordinary, non-debuggable QA app process showed zero capabilities, `NoNewPrivs=1`, `Seccomp=2` and ten syscall filters. An experimental app-library autoload package installed and became visible, but the expected native report and loaded-library mapping were not observed. In-process native qualification remains incomplete; this failed integration experiment does not establish that native modules generally cannot work.

The original [container probe](../examples/android-runtime/container_probe.c) compiles for ARMv7, AArch64 and x86_64. Only x86_64 was executed. Namespace trials occur in bounded disposable children and never mount a filesystem, register Binder services, alter kernel settings or modify the calling process's namespaces. No physical device was touched.

### Decision

The conventional private-Binder Android-container route is blocked **in the tested emulator configuration**. Kernel support for user namespaces does not establish permission to create them. Existing Vega Binder devices must not be appropriated for an Android service manager. Linux documents that separate binderfs instances provide independent Binder devices; this image lacks that facility. [Linux binderfs documentation](https://docs.kernel.org/admin-guide/binderfs.html).

This result does not prove that every Vega device or a future supported platform integration is incapable of hosting Android. It does rule out treating Waydroid as an installable, ordinary Vega app on the strength of the current results. A reusable userspace IPC/framework compatibility design or a complete software-emulated guest would be separate experiments. Neither is implemented or performance-qualified. A supported platform integration would need Amazon's cooperation and a kernel/security configuration that permits the required facilities; no such change has been requested or applied.

The workbench's read-only runtime report reads selected kernel options and reports this conventional-container blocker without claiming APK execution or container readiness. Unreadable configuration stays unknown. Automated regression checks cover enabled versus disabled versus unavailable configuration. The container checks were part of the 118-test research baseline; see the 0.5.0 release verification for workbench and updater coverage.

## Software guest experiment — November 8, 2026

An external Android-x86 9.0-r2 image and an external Linux QEMU runtime were tested privately inside the Vega development VM using software TCG CPU emulation, with no nested KVM. Android reported framework boot completion, and installation of an unchanged original APK returned success. Those milestones did **not** establish app execution: launch did not produce a qualified app UI. Runs encountered a blocked rendering path, system-server watchdog restarts and impractically slow first-boot work. A later attempt to use host-side llvmpipe software graphics through a virtual GPU ended in a QEMU segmentation fault.

The Android media and target APK were not rewritten or resigned. The experiment used private guest configuration and a separate guest data image; none of those external system images, runtimes, test APKs or private logs are distributed with Studio. This is not the supported Vega emulator integration described in [the workbench guide](WORKBENCH.md).

A separate bounded physical Fire TV Stick 4K Select test ran a 128 MiB, kernel-only software guest far enough to enter Android's init. It did not boot an Android framework or run an APK on the device. Its 32-bit application ABI and roughly 1 GiB total RAM remain significant limits. No host kernel, firmware, security setting or existing application was changed.

The unchanged-APK gate remains **not passed**. Installing an APK, showing a boot logo or reaching a framework boot property is insufficient. A future runtime must demonstrate the app's actual UI, input, behavior, resource use and isolation before any conversion/runtime interface is offered as functional.
