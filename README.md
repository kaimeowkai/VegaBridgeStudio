# VegaBridge Studio

A native Windows workbench for creating and testing Amazon Vega apps: editor, project templates, real Vega VM host, USB/Wi-Fi device tools and an integrated coding assistant.

**0.2.0 is an independent community developer preview.** It runs its host tools directly on Windows. It requires your own Amazon SDK target files and virtual-device images for SDK and emulator features. It is not affiliated with Amazon or OpenAI and does not redistribute Amazon's SDK.

## Start on Windows

Download the Windows x64 ZIP from [GitHub releases](https://github.com/kaimeowkai/VegaBridgeStudio/releases), extract the entire folder, and run `VegaBridgeStudio.exe`. Keep `_internal` beside the executable. `VegaBridgeCLI.exe --help` provides the command-line companion. The package is not Authenticode signed.

Choose **Settings** to configure your complete Windows Node/npm installation and Android platform-tools `adb.exe`. Studio uses a separate bridge port, 5048 by default. Native cross compilation additionally needs Windows LLVM/LLD and the matching owner-supplied SDK sysroots. Optional tools are OpenSSL, the official TurboModule generator's `cli.js`, and a compatible Windows Hermes compiler. These third-party tools are external prerequisites.

Create a blank JavaScript/TypeScript project or choose one of the 20 original sample templates. **Build package** installs the project's pinned dependencies, bundles source and signs a development VPKG. **Install + run** targets the online device selected in the toolbar. Build trusted projects only: npm scripts and project build configuration execute with your local privileges.

## Integrated development assistant

Use **ChatGPT accounts → Continue with ChatGPT**, complete OpenAI's browser consent, and choose an available model. Studio uses its own public-client OAuth flow and encrypted token store. It never reads ChatGPT, Codex or another application's credential files. You can also configure an API key or a compatible local endpoint. Account availability, supported models and usage limits depend on the provider.

**Workspace agent** uses Responses function calls to create projects, inspect and edit current project source, build, select connected targets, install/run, send remote keys and change the IDE theme. Ask it to do the work directly. It has no arbitrary shell tool. File writes require the current file hash and refuse unsaved editor buffers. **Undo last assistant edit** restores the most recent edit if no newer change would be overwritten. **Stop** cancels the active assistant task. Compatible endpoints without Responses tools can use **Discussion only**.

Planning context survives creating or opening projects. **New chat** starts a separate discussion; **Saved conversations** resumes earlier discussions. Conversations, drafts, OAuth sessions, API keys and edit backups use Windows CurrentUser encryption outside all projects. They are not included in source exports, example projects or release packages. Nothing in your personal chat history is supplied with this software. When you send a message, the current discussion and source requested by workspace tools go to your chosen model endpoint. Screenshots remain local.

## Device Lab and emulator

Enable Amazon Developer Mode. For wireless testing, choose TCP/IP mode and connect the device's address in Device Lab. For USB, use a data cable and choose **Find USB devices**. Changing the device's connection mode can require a reboot. Only authorized online targets can be selected. Physical USB behavior requires compatible hardware/drivers; consult the verification receipt for actual tested transports.

Device Lab provides install/run, remote keys, text input, screen capture, package/lifecycle inspection, app logs and user-directed file transfers. Its manual developer shell uses the privileges Amazon grants to Developer Mode. Uninstall can remove app data. No rooting, firmware flashing or DRM bypass is provided.

**Keep awake during testing** sends the developer WAKEUP key periodically for a bounded session. It does not change sleep settings or promise to keep a television powered on, and it is not a production app wake-lock API.

For a real local emulator, configure a Windows QEMU distribution including GTK/OpenGL/virgl and `qemu-img.exe`, your matching Vega VVD `image_files` folder, and a separate writable VM folder. Start the native VM, wait for its ready screen, then connect it to Device Lab. Source SDK images remain read-only; guest writes persist in a private overlay. Studio permits one visible IDE instance and one managed VM. WHPX must already be enabled; Studio does not change Windows security or hypervisor settings. TCG is available but not performance-qualified.

The optional remote VVD controls remain available for an already-configured Ubuntu/macOS SDK host. They are not required for the native Windows path.

## Languages and SDK tools

- **JavaScript / TypeScript / TSX:** editable React Native/Kepler projects and bundled app builds. TSX is transpiled by Metro; this is not a claim of full semantic TypeScript checking.
- **C / C++:** native Windows LLVM cross compilation against matching SDK sysroots for ARMv7, AArch64 and x86_64, plus shared-library output and ELF architecture checks. Basic C/C++ programs run on the physical ARMv7 target and x86_64 emulator. Platform API modules still require their SDK headers, contracts, libraries and app integration.
- **TurboModule codegen:** run Amazon's JavaScript generator on Windows to produce C++ interfaces and implementation scaffolding from TypeScript. Existing implementation folders are protected from accidental overwrite.
- **Hermes:** optional Windows bytecode compiler tool. Bytecode must match the target runtime; consult actual verification results before using it for a release.
- **HTML/CSS/JavaScript web content:** Vega exposes a documented WebView integration; the core gallery uses native React Native views. This release does not advertise an independent browser-app packaging target.

The package validator checks exact payload hashes, manifest requirements, native ELF architecture and both detached CMS signatures using configured OpenSSL. Mathematical signature verification does not establish a trusted certificate chain or Amazon approval. Generated development keys must never replace an existing published application's signing identity.

This remains a partial Windows host-tool implementation, not a complete binary conversion of every SDK API or a source debugger. Emulator success does not establish IAP, DRM, media, peripherals, physical-device behavior or Amazon certification parity.

## Ten included themes

Harbor Dark, Matrix, Daylight, Midnight Blue, Solar Ember, Orchid Night, Forest Canopy, Arctic Light, Rose Quartz, High Contrast. Choose Settings → Appearance for a live preview, then Save. The editor, assistant, output, menus and controls follow the selected palette. See [theme details](docs/THEMES.md).

## Samples, versions and source

The gallery includes 15 useful app starters and five original games with distinct visual directions and local interaction. See [the sample gallery](docs/SAMPLE-GALLERY.md), [version history](CHANGELOG.md), [SDK port notes](docs/WINDOWS-SDK-PORT.md) and [security notes](SECURITY.md). Screenshots are actual emulator captures of synthetic sample projects.

Both [0.1.0](https://github.com/kaimeowkai/VegaBridgeStudio/releases/tag/v0.1.0) and [0.2.0](https://github.com/kaimeowkai/VegaBridgeStudio/releases/tag/v0.2.0) have separate release notes and downloads. The older release remains an archive; use 0.2.0 for ChatGPT sign-in, direct assistant tools and the redesigned gallery.

To build from source, use Python 3.12 on Windows, create `.venv`, install `.[dev]`, run `python -m pytest -q`, then `scripts/build-windows.ps1 -OutputDirectory dist-v0.2.0`. Third-party notices accompany the portable package. Original project code is MIT licensed.
