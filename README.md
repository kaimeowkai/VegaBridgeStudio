# VegaBridge Studio

A native Windows desktop workbench for developing JavaScript apps for Amazon Vega OS. Independent community software; not affiliated with or endorsed by Amazon or OpenAI.

**0.1.0 is a review preview, not a complete Vega SDK port.** The editor, build/packager, assistant, device controls, and QEMU emulator host run in native Windows processes. No WSL, Docker or remote Linux host is required. The VM boots the owner-supplied Vega guest OS; its QEMU engine and SDK images are external prerequisites rather than bundled redistribution.

## Features

- Project tree, tabbed editor, syntax highlighting, line numbers, find, undo and save.
- New Kepler 4 / React Native 0.83 JavaScript template with pinned npm dependencies and Windows-compatible Metro module IDs.
- Build a development-signed `.vpkg` with the native Windows packager. Signing keys are encrypted with Windows CurrentUser DPAPI outside project folders.
- Discover USB and Wi-Fi devices; install VPKGs, request app launch, stop/uninstall apps, inspect packages and lifecycle, push/pull files, capture screens and send remote buttons.
- Developer shell and cancellable live project logs. A dedicated local bridge port avoids restarting other tools' bridge servers.
- Coding chat through OpenAI's Responses API or a compatible Chat Completions server, including loopback local models. Attach only an explicitly previewed file/selection. Review suggested replacements as a diff before applying to the editor.
- A native Windows Vega VM manager using QEMU, virtio graphics, a read-only virtual GPT disk and a separate persistent QCOW2 overlay. No multi-gigabyte image copy is required. An optional SSH adapter remains available for an existing official Ubuntu/macOS VVD.

## Run the Windows executable

Requires 64-bit Windows 10 1903+ or Windows 11. Extract the entire portable ZIP and run `VegaBridgeStudio.exe`. Keep `_internal` next to the EXE. Python is bundled. Windows' system ICU libraries are used; MSYS/Git ICU copies are deliberately excluded from the build. This preview is not Authenticode signed; no publisher certificate has been configured. Do not redistribute a build as a signed production release.

Open **Settings → Windows tools** and select:

1. `node.exe` from a full Windows Node.js 22.14+ installation with npm.
2. `adb.exe` from official Windows Android platform-tools. Its bridge protocol works with the tested Vega OS 2.0 Fire TV Stick. This is a community compatibility path, not Amazon-supported Windows VDA.
3. A dedicated bridge port; default is 5048.

Create a project, choose its title and package ID, and select **Build package**. First build downloads the pinned npm dependencies. **Install + run** builds again, installs on the selected device, and sends its launch request. Use the screen capture and lifecycle output to verify successful execution; a launch request alone is not proof of app startup.

Only open/build projects you trust. npm install/build can execute project and dependency scripts. This IDE is not a sandbox.

## Connect a Vega device

Enable Amazon Developer Mode on the device. For wireless select TCP/IP mode, put the PC on the same network and connect its IP in **Device Lab**. For USB select USB mode, connect a data cable and choose **Find USB devices**. Switching the device connection mode may require a reboot. Offline and unauthorized devices cannot be selected for operations. Physical USB testing depends on compatible hardware and drivers; discovery parsing is tested but no USB hardware session is claimed in this preview's verification receipt.

The developer shell works with the privileges granted by Vega Developer Mode. It does not root, jailbreak, bypass licensing or reflash Vega OS. Uninstall may remove app data. File transfers use the source and destination selected by the user.

## AI setup

In **Settings → AI assistant**, choose the endpoint, protocol and model, and enter your API key in the password field. No key is bundled. Keys are encrypted locally with Windows DPAPI and bound to the chosen endpoint. A loopback HTTP server may be used for a locally running model; remote endpoints require HTTPS. Configure the model name supported by your provider/account. The editable default follows the official OpenAI examples and is not a promise of account availability.

ChatGPT account sign-in is not implemented in 0.1. API keys and local models are the implemented connection methods. ChatGPT plan usage integration is a separate official OAuth flow; this app never reads another app's login tokens.

Prompts, previous conversation turns, and approved file context are sent to the selected endpoint. Chat remains in memory until cleared or the project changes. The assistant has no access to the console, device, tools, or filesystem; suggested file changes require manual diff review and save. Review code before running it. Server bodies and authorization headers are not copied into error output.

## Native Windows Vega emulator

Obtain the Windows QEMU distribution linked from [QEMU's official download page](https://www.qemu.org/download/), and the matching Vega Virtual Device distribution through Amazon's developer tools. Extract the VVD's `image_files` directory locally. Do not run the Linux host executables; the native manager uses only the guest development images. This app does not accept terms, download SDKs or redistribute images on your behalf.

In **Settings → Native emulator**, select the Windows `qemu-system-x86_64.exe`, your VVD `image_files` folder, and a separate writable VM folder. The QEMU distribution must include `qemu-img.exe`, GTK/OpenGL and virgl support. WHPX must already be enabled/available on Windows; the IDE does not change hypervisor or security settings. Software TCG is selectable but has not been performance-qualified.

Choose **Emulator → Start native Vega VM**. The guest opens in a separate native QEMU display window. Initial setup can reboot. After its ready screen appears, choose **Connect VM to Device Lab**. Build, install, launch and remote commands then use the selected loopback target just like a physical target. The Windows bridge uses the legacy shell protocol with explicit remote exit-status checking to support both tested Vega device types.

Source images are opened read-only by a private loopback NBD service. Guest writes are saved in the chosen folder's `userdata.qcow2`; no changes are written to Amazon's source images. Disk source metadata prevents silently reusing an overlay with a different image set. Keep the overlay and `Image-Source.json` together. **Stop native VM** asks QEMU to flush its disks and quit; save app work before stopping. Closing the QEMU window also ends that VM session. A crashed guest can still require its normal filesystem recovery on next boot.

VM screenshots first use QEMU's monitor API; accelerated displays without a CPU surface fall back to Windows Graphics Capture, restricted to this Studio-launched QEMU process/window. The desktop monitor and unrelated windows are never selected. Keep the VM window open and restored when capturing. Physical device captures retry only the SDK's known transient atomic-display-commit error.

The tested path uses Vega SDK/VVD 2.0.13986 with Windows x64 QEMU 11.1 and WHPX. Boot, the real VVD ready screen, bridge shell, and installation/launch of a Windows-built React Native sample were observed. That is not complete peripheral, performance, DRM, IAP, audio/video or Amazon certification parity. Test final releases on a physical Fire TV. See [Windows SDK port notes](docs/WINDOWS-SDK-PORT.md).

## Supported build scope

The native build supports the bundled **Kepler 4 JavaScript-only template**, uses the device system React Native runtime, and emits a development package whose filename retains the original ARMv7 physical-device target. Its JS-only payload also ran in the x86_64 VM; this does not establish cross-architecture compatibility for native libraries. It does not compile custom ARM/C++ modules, compile Hermes bytecode, run strict ABI validation, produce an Appstore submission, provide a source debugger, or port all Amazon SDK APIs. Existing SDK projects can be viewed/edited; unsupported builds fail explicitly rather than silently generating a purported complete package.

The built-in inspector verifies the payload inventory and SHA-384 digests, and reads the CMS certificate. It does not cryptographically verify CMS signatures or establish signer trust; the Vega installer performs signature validation. A self-signed development certificate is not an Amazon-issued production identity. Never replace an existing published app's signing identity with a generated development identity.

Signing identities and preferences live in `%LOCALAPPDATA%\VegaBridgeStudio`. DPAPI credentials are tied to your Windows user/machine. Preserve that directory if you need the same development identity after moving a project. This preview has no cross-machine signing-key export/import UI. Captures and task output can contain private device details; review before sharing them.

## Build from source

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe run_studio.py
.\scripts\build-windows.ps1
```

The build produces an unpacked app, portable ZIP, source ZIP and SHA-256 checksums in `dist/`. No Amazon SDK, emulator image, Node installation, platform-tools, API key, signing key, user project or private SDK inspection material is included. Download those developer prerequisites from their official sources under their own terms.

## References

- [Amazon SDK requirements](https://developer.amazon.com/docs/vega/2.0/install-vega-sdk)
- [Vega device tools](https://developer.amazon.com/docs/vega/2.0/vda-tools)
- [Official Vega Virtual Device](https://developer.amazon.com/docs/vega/2.0/run-apps)
- [OpenAI streaming responses](https://developers.openai.com/api/docs/guides/streaming-responses)
- [Official ChatGPT plan integration](https://developers.openai.com/siwc/token-sharing-open-source)

MIT applies to original VegaBridge code. Third-party components retain their licenses; see `THIRD_PARTY_NOTICES.md` and the generated distribution's `licenses/` directory. The Amazon npm dependencies are fetched at build time, not redistributed in the studio source package.
