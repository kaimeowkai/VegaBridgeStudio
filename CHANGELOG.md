# Changelog

## 0.5.0 — Integrated emulator and device workbench

- Original VegaBridge emulator panel with docked and pop-out layouts sharing one managed QEMU VM. Local GPU display mirroring with a bounded latest-frame queue, a refreshed-image fallback, remote buttons, focused-preview keyboard navigation, pause/resume, and identity checks before VM control.
- Fit the guest display to its engine window. Start/attach waits for an authorized bridge and responding Vega package service before selecting the VM; stopping the VM cancels that connection wait.
- Private named USB/Wi-Fi connection bookmarks, target inspection, selected-target Wi-Fi reconnect, and offline/authorization guidance. Discovery no longer cancels a wake session when the selected target stays the same. No global bridge reset or device connection-mode changes.
- Command palette (Ctrl+Shift+P), fuzzy Quick open (Ctrl+P), Go to line (Ctrl+G), current-file replacement with one-step Undo (Ctrl+H), line comments (Ctrl+/), and selected-line indentation/outdent. Build: Ctrl+Shift+B; install/run: Ctrl+F5; emulator: Ctrl+Shift+E.
- Installation removes only its own temporary package upload and waits for the launched component to become VISIBLE in Vega lifecycle.
- Public GitHub update checks, Preview/Stable channels and optional automatic download/install on the next clean exit. Verify the GitHub asset digest, checksum file, archive paths and complete installation manifest. A separate portable updater waits for Studio to exit, preserves the previous installation, and restores it if replacement fails. Projects and private per-user state are excluded.

### Android migration assessment prototype

- Read-only Android source/APK assessment through the source CLI, with Android API indicators, dependency inventory, logic-review candidates and a separate migration plan.
- Bounded input reads, explicit incomplete-scan reporting, private/generated path exclusion and no dependency execution or device changes.
- Document a source-first Android-to-Vega methodology. This prototype does not execute APKs or translate applications automatically. It was absent from the 0.4.0 executables.
- Add the native Windows compatibility workbench: source/APK input, separate planning workspace, shared adapter choices/review notes, plan preview and runtime prerequisite observations.
- Gate workspace creation on before/after source fingerprints; refuse overlapping paths, changed inputs and existing output folders. Original source and signing material are never copied.
- Add a non-destructive native Binder/KVM version-query sample. Three architectures compile; the actual x86_64 emulator returned Binder protocol 8. This is a research prerequisite, not Android app execution.
- Extend runtime reports with selected running-kernel configuration, namespace limits and an explicit private-Binder container blocker. Add a bounded child-only namespace/memfd research probe; actual x86_64 developer-context trials returned EPERM for namespace creation, and the checked kernel disables binderfs. No Android runtime or APK execution is implemented.

## 0.4.0 — Installed apps and JavaScript debugging preview

- Attach Windows CodeLLDB to the current project's installed Vega component. Inspect its native stack, registers and disassembly, then detach without terminating the app. Optional matching project symbols enable native source lookup.
- JavaScript/TypeScript/JSX source breakpoints, stepping, stack, locals and console evaluation through the installed app's Hermes inspector. Metro source maps show original project files; mismatched running bundles and stale source are refused.
- Separate development VPKGs preserve release output and signing identity. Studio owns its loopback Metro child, chooses a free host port, and manages only its own device reverse mapping. Per-app debug-launch timeout protection supports long breakpoint pauses; stopping owned Metro clears that setting for subsequent normal launches.
- Restore the assistant with the toolbar's **Show assistant** button or **Ctrl+Shift+A**. Include an actual Studio screenshot with the default assistant introduction and synthetic debugging data.
- Fix development-server logging lifetime, strip terminal escape sequences, and retain explicit cleanup errors for disconnected targets.

Qualified on the actual x86_64 Vega VM. ARM installed-app attachment, app-owned C++ module source symbols, hot reload and full React Native DevTools are not qualified by this release. Existing 0.1.0–0.3.0 downloads remain available.

## 0.3.0 — Native debugging and API tools preview

- Native source breakpoints, continue/pause, stepping, call stack, source preview, locals and expandable registers through Windows CodeLLDB and a matching target lldb-server.
- Session-owned developer executable launch and cleanup; dedicated loopback bridge forwarding. Actual x86_64 Vega VM and Studio GUI checks.
- Native Windows APMF IDL-to-C++ generation using external SDK tools, with private host-shell and dependency-file compatibility. Originals remain intact; signed or unexpected SDK JARs are refused.
- Read-only SDK header/contract/library browser; configurable include directories, link libraries and debug-symbol compilation. SDK APMF linker-script integration.
- Separate debugger/platform API settings and native code samples. No proprietary SDK materials or private sessions are bundled.

This release qualifies standalone native debugging and an APMF base-library program. Installed-app native attachment, JavaScript debugging and individual privileged platform services remain future work. The 0.1.0 and 0.2.0 downloads are preserved.

## 0.2.0 — Integrated development preview

- Official app-owned ChatGPT sign-in, account selection, model catalog, refresh and sign-out; API-key/local-endpoint options remain available.
- Direct Responses workspace assistant: create projects, inspect/edit source, build, install/run, select devices, send remote input and change themes. Bounded tools, stale-write checks, encrypted undo and cancellation.
- Private encrypted conversation history and drafts; planning survives new/open projects and restarts. Saved-conversation picker and separate new chats.
- Twenty original standalone sample templates, including five games, with distinct art directions and richer interaction. Emulator screenshots and gallery documentation.
- Ten themes with a live settings preview, including Matrix, Daylight and High Contrast; project-wide search, single-instance desktop activation and one managed native VM.
- Native Windows LLVM C/C++ cross compilation for three Vega target architectures, ELF checks, TurboModule code generation, optional Hermes bytecode compilation and cryptographic CMS validation.
- Developer test wake sessions, private device text input, lifecycle-based launch verification, bounded physical screen capture and managed-VM capture/stop across GUI/CLI sessions.
- Windows command-line companion and updated external-tool setup documentation.

No private user conversation, credential, account record or development log is included. This remains a partial community SDK host implementation; release-specific verification documents identify actual tested paths and limits.

## 0.1.0 — Initial Windows review preview

- Native Qt editor, project tree, manual file replacement review and text-only API-key/local-model assistance.
- JavaScript Kepler starter, Windows Metro path adaptation, development VPKG signing and payload-digest inspection.
- USB/wireless bridge discovery and developer device controls.
- Native Windows QEMU Vega guest host with private overlay and owned-window capture; optional remote VVD controls.
- Portable Windows x64 and source review ZIPs with checksums, notices and build instructions.

0.1.0 does not include ChatGPT account sign-in, direct assistant execution or the 20-template gallery. Its original archived downloads are preserved unchanged.
