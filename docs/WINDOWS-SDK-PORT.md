# Windows SDK port notes

This project replaces selected Vega host tools with native Windows implementations. It is not a binary conversion of the complete Amazon SDK, and it does not redistribute decompiled vendor source.

| Component | Windows implementation | Verification / limit |
| --- | --- | --- |
| Project creation/editor | Native PySide6 desktop UI | Opens, edits and saves the bundled JS project |
| JS bundling | Windows Node, Metro and public npm Kepler packages | Portable module IDs patched within the project's own node_modules |
| Development packager | Python, FlatBuffers, SHA-384, detached CMS, zstd USTAR | Packages accepted by physical Vega and the VM |
| Device transport | Windows platform-tools, dedicated bridge port | Physical Wi-Fi and loopback VM; USB discovery implemented, physical USB test not claimed |
| Shell compatibility | Legacy protocol with an explicit per-command exit marker | Handles the VM's different default shell service naming; does not confuse a successful connection with command success |
| Virtual device launcher | Native Windows QEMU, virtio GPU, WHPX, private read-only NBD image mapping | Real Vega GUI and sample app launch observed |
| VM persistence | QCOW2 overlay; SDK images remain read-only | Per-VM source inventory and stable GPT identifiers |
| Coding assistant | HTTPS Responses / compatible Chat Completions adapter | Mock stream/error tests; real provider use requires the owner's own key |
| Custom target C/C++ compilation | Not ported | Requires a validated Windows cross-toolchain/SDK integration |
| Native source debugging / Hermes / strict ABI checks | Not ported | Not advertised as available |

The local interoperability investigation inspected the SDK's ELF host tools and symbols, recovered launcher behavior, and examined the package and guest disk formats. The included source implements the Windows workflows independently; proprietary SDK inspection files, binaries and guest images are excluded from GitHub/source packages.

An initial trial using an installed stock Android Windows emulator misdetected the guest architecture and later failed in graphics initialization. The working path uses upstream Windows QEMU directly, a correctly named GPT partition layout, and virtio graphics. A minimal kernel probe intentionally ran `uname` as PID 1 and ended with the expected init-exit panic; that probe is not the full-boot evidence. Subsequent full guest boots reached the actual Vega Virtual Device ready screen and launched the development package.

Only the JS sample path is qualified so far. The VM's hardware services differ from real Fire TV and may emit service warnings. Do not infer DRM, purchasing, media, sensor or production compatibility from a successful basic app launch.
