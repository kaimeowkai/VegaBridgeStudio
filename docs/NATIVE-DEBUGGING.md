# Native debugging and platform APIs

Studio 0.4.0 supports both a **separate C/C++ developer executable** and **attachment to the current project's installed app**. JavaScript/Hermes has its own [debugger tab and guide](JAVASCRIPT-DEBUGGING.md). SDK 2.0.13986, an x86_64 Vega VM and CodeLLDB 1.12.3 / LLDB 22.1.8 were used for the end-to-end checks.

## Configure external tools

Install your Windows LLVM/LLD toolchain and matching owner-supplied SDK sysroots as described in [Windows SDK notes](WINDOWS-SDK-PORT.md). In **Settings → Native debugger**, select the Windows `codelldb.exe` and the **matching-version Linux `lldb-server` for the target architecture**. CodeLLDB is an external open-source dependency, not bundled with Studio: [official releases](https://github.com/vadimcn/codelldb/releases), [manual](https://github.com/vadimcn/codelldb/blob/master/MANUAL.md).

The Windows and Linux server packages must use the same LLDB version. Do not point the server field at a Windows executable. The qualified x86_64 server uses a private interpreter-path compatibility copy for Vega; the downloaded original remains intact. ARMv7 and AArch64 debug sessions need their respective servers and remain unqualified by this release's emulator check.

## Debug a native executable

1. Open a project and a C/C++ file, such as [the calculation sample](../examples/native-debugging/calculate.c).
2. Select the online Vega emulator in the toolbar. Select `x86_64` in **Native debugger**.
3. Click **Compile current C/C++ with symbols**. This compiles one translation unit with `-O0`, DWARF 4 and frame pointers. Multi-file builds need your own build system and a symbol-bearing executable inside the project.
4. In the Code tab, click the source gutter or press **F9** to toggle a breakpoint. Breakpoints are session-local; recheck line positions after editing. Recompile after source changes.
5. Click **Start native debugger**, then **Continue** to reach the breakpoint. Inspect source, stack, locals, expandable values and registers. Use **F10** to step over, **F11** to step into and **Shift+F11** to step out. **F5** starts/continues; **Shift+F5** stops.
6. **Stop debugger** cleans up its own target/server processes, bridge-forward mapping and remote temporary directory. Stop before changing projects. The emulator and unrelated apps remain running.

The developer program runs in its own `/tmp` directory under Developer Mode privileges, rather than inside an installed application's identity or permissions. It must be an executable; a shared library needs a developer harness. The debugger's TCP endpoints bind to loopback. Studio does not change global ptrace, sandbox, SELinux, ASLR or device sleep settings. Debugging may alter timing and program execution. Debug artifacts and session copies are private local files; they are not included in release exports.

## Attach to the current project's installed app

1. Install and run your project's development app on the selected local USB/TCP target. For a React Native app, **JavaScript debugger → Build + run development app** also configures per-app breakpoint timeout protection. Keep that owned Metro session running while testing either debugger. Otherwise, use Amazon's documented `vlcm debug <component-id> --disable-app-timeout` before launching your app. An unprepared app can be terminated by Vega's heartbeat watchdog while paused.
2. Select **Attach installed project app** in **Native debugger**. Optionally select a matching unstripped project library or executable for source symbols. The field may be empty to inspect registers, stack and disassembly.
3. Click **Attach installed app**. Studio verifies the current project's lifecycle instance, enters that component's developer shell namespace, and attaches its own matching LLDB server to the app process. It does not attach to Amazon system components.
4. Continue/pause or inspect the stopped stack and registers. Source breakpoints require matching loaded native code and unstripped symbols; JavaScript locations belong in the JavaScript debugger instead. The x86_64 check qualifies native attachment and disassembly, not source symbols in an app-owned TurboModule.
5. **Detach; keep app running** resumes and disconnects from the app. Studio removes only its own server, adapter, forwarding and scratch directory. Finish by stopping owned Metro; this clears that component's debug-launch overrides. Relaunch normally for normal timeout behavior. If you prepared it manually, run `vlcm debug <component-id> --clear` yourself and relaunch.

The GUI and backend inspected an actual installed x86_64 app. With the per-app timeout protection prepared before launch, the process survived a long native breakpoint pause and detach. Individual platform service calls, ARM attachment and app-owned C++ source-module integration require further qualification. For timeout details, see [Amazon's debugging issue guide](https://www.developer.amazon.com/docs/vega/0.24/debugger-issues).

## Generate and use APMF C++ bindings on Windows

Provide these owner-supplied SDK inputs outside Studio's distribution:

```text
<API root>/
  x86_64/include/apmf/...        # SDK headers and apmf/iface/... .idl contracts
  x86_64/lib/libapmf.so         # matching target runtime import library
  armv7/include/...             # optional other architectures
  armv7/lib/...
  aarch64/include/...
  aarch64/lib/...
  tools/apmf.ld                 # SDK linker section definitions
```

In **Settings → Platform APIs**, choose that API root, the original SDK `apmfc.jar`, a Windows JDK compatible with that compiler, and Git for Windows `sh.exe`. The qualified JAR comes from APMF2Dev 2.0.30257.0 in SDK 2.0.13986. Other SDK layouts or compiler versions may require additional work.

Use **Tools → Generate platform API C++ bindings** and choose a new/empty output directory, package names such as `com.amazon.apmf, com.amazon.kepler.device_config`, and matching architecture. Or run:

```powershell
VegaBridgeCLI.exe api-codegen com.amazon.apmf com.amazon.kepler.device_config --arch x86_64 -o .\build\platform-api
VegaBridgeCLI.exe compile .\apmf-string.cpp --arch x86_64 --debug -I .\build\platform-api\include -l apmf -o .\build\apmf-string
VegaBridgeCLI.exe sdk --arch x86_64 --search device_config
```

The generator runs Windows Java and Windows Clang. A private JAR copy substitutes its hardcoded Linux shell path with Git for Windows; the independent preprocessor adapter normalizes Windows dependency files. The original JAR is preserved. Signed JARs and unexpected host classes are refused. This release does not distribute Amazon's JAR, generated SDK bindings, libraries, header packages, images or inspection dumps. Generated bindings stay in the selected project folder; follow your SDK agreement for their use and distribution.

**Tools → Compile C / C++ source** accepts semicolon-separated include directories, comma-separated library names and a debug-symbol option. Linking `apmf` also uses the SDK's external `tools/apmf.ld`. The **SDK browser** searches header, contract and library paths and displays text read-only. A matching header alone does not establish permission or runtime availability.

## Actual verification and remaining scope

- In the real Vega VM, the Windows adapter stopped at a C source breakpoint on line 5, showed `seed = 7` and `answer = 12`, stepped to line 6 and showed `answer = 24`. The GUI exercised compile, start, continue, step and stop; the backend also verified exit code zero.
- The native Windows IDL path generated 455 files for APMF and device-config packages. A C++ program using the generated APMF headers and `libapmf` printed `WINDOWS_VEGA_API_OK 19` in the VM and exited successfully.
- This checks APMF base-library interoperability. It does **not** qualify invoking the device-config service, installed app components, TurboModule lifecycle attachment, media/DRM/IAP services or privileged APIs. Those require declared contracts, appropriate app identity, SDK-specific integration and runtime tests.

Amazon's platform-specific workflow remains the reference for platform debugging: [official debugging documentation](https://developer.amazon.com/docs/vega/2.0/debugger). Studio reduces the native Windows gap without claiming complete SDK parity.
