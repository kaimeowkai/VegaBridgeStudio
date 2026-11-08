# Windows SDK host tools

VegaBridge implements selected host workflows directly on Windows. It does not redistribute a decompiled Amazon SDK or claim complete SDK API/debugger parity. SDK headers, target libraries and guest images remain external owner-supplied inputs.

| Workflow | Implementation and actual check | Limit |
| --- | --- | --- |
| Project/editor | Native Qt, JavaScript/TypeScript/TSX templates, source search, ten themes | Metro transpiles TypeScript; full language-server diagnostics are not provided |
| Coding assistant | App-owned official ChatGPT OAuth; live Responses tool calls created/edited/built/deployed a separate synthetic app | No private Codex tokens, arbitrary shell or public chat transcripts |
| Conversations | Windows-encrypted local discussion/drafts, saved chat picker, planning retained through project creation and restart | Provider receives the discussion/source used for a sent request |
| JS app build | Windows Node, Metro and pinned public Kepler packages | Native modules need additional integration |
| VPKG | Windows Python, FlatBuffers, SHA-384, detached CMS, zstd USTAR | Development signature is not Amazon approval |
| Package validation | Exact payload inventory/hashes, required manifest fields, ELF architecture, both CMS signatures checked with OpenSSL | Signer-chain trust is not established by mathematical verification |
| C/C++ | Windows LLVM/LLD against matching ARMv7, AArch64 and x86_64 sysroots; executable and shared-library output | Basic C/C++ programs executed on physical ARMv7 and the x86_64 VM; AArch64 compilation verified without AArch64 hardware |
| x64 guest loader | Explicit Vega `/lib/ld-linux-x86-64.so.2` interpreter | Avoids generic Linux `/lib64` runtime failure |
| TurboModule generator | Official JavaScript generator ran on Windows and emitted C++ spec/header/implementation files | Implement and link SDK-specific modules before using the generated scaffolding |
| Hermes bytecode | Windows compiler emitted HBC 98; its signed test app rendered on the actual x64 VM and physical Fire Stick | Compiler/runtime versions must match; this does not qualify arbitrary Hermes releases |
| Device bridge | Windows platform-tools, dedicated server port, explicit shell exit marker | Wi-Fi and loopback tested; physical USB compatibility depends on hardware/drivers |
| Device input/capture | Remote keys, private text input, bounded screenshots, lifecycle-based launch check | A connected bridge or accepted launch is not proof of a visible app |
| Developer wake session | Periodic WAKEUP key, bounded and cancelable; does not alter OS settings | No production app wake-lock API; does not promise TV power control |
| Real Vega emulator | Windows QEMU/virgl/WHPX, read-only NBD image mapping and private QCOW2 overlay | SDK/VVD 2.0.13986 and QEMU 11.1 qualified path; TCG not performance-qualified |
| VM ownership | Singleton lock plus monitor identity; GUI/CLI managed-session attach, stop and capture | Only the owned VM is controlled/captured |
| Sample gallery | All 20 apps built, installed and visibly exercised in the actual VM; five games have progression checks | Separate physical app release checks are still necessary |
| Native source debugging | Windows CodeLLDB, matching target lldb-server, DAP breakpoints/stepping/stack/locals; actual x64 VM and GUI exercised | Separate developer executables; installed-app and JS/Hermes source debugging are not implemented |
| Platform API bindings | Windows Java APMF generator with private host-path/dependency adapter; generated C++ plus libapmf executed in the VM | External SDK inputs required; service permissions and installed-app integration remain application-specific |

See [native debugging and API setup](NATIVE-DEBUGGING.md) for tool versions, instructions and the exact qualification limits.

The interoperability investigation inspected host binary formats/symbols, package structure and guest disk layout. The public source is the independent Windows implementation. Proprietary binaries, sysroots, guest images, inspection dumps, credentials and personal logs are excluded.

The actual VM boots the Vega guest OS. A successful JS sample or native console probe does not establish complete media, IAP, DRM, sensor, peripheral, timing or Appstore certification parity. Keep your existing production signing identity when updating an existing app.
