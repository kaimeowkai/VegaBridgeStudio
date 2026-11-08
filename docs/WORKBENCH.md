# Emulator and device workbench

VegaBridge Studio 0.5.0 adds an original Qt interface around the external QEMU engine. It does not replace QEMU or redistribute Amazon images.

## Emulator in the IDE or a pop-out

1. Configure Windows QEMU and your matching Vega VVD image files in Settings → Native emulator.
2. Open **Emulator** with **Ctrl+Shift+E** and choose **Start / attach**. An existing managed VM is reused. Starting a new VM preserves its private writable disk and keeps SDK source images read-only.
3. Studio waits for the authorized device bridge and Vega's package service. When ready, the VM becomes the toolbar target.
4. **Live emulator display (Windows)** mirrors only the managed QEMU GPU window into the panel, with engine chrome cropped out. Updates are capped at ten per second; the latest-frame mailbox drops old frames instead of accumulating images. **Pop out emulator** moves that same panel into its own resizable window; **Dock emulator** or closing the pop-out brings it back. Neither action starts another VM.
5. The external engine window stays available and must remain restored for Windows Graphics Capture. It may sit behind the IDE. This integration is a local GPU mirror, not a headless QEMU backend or a replacement CPU emulator. Disable live display to use the local refreshed-image preview. That fallback updates every two seconds while visible, allows one capture at a time, and pauses after three failures.

Remote buttons always address the managed VM, regardless of which physical device is selected in the toolbar. Both display modes accept arrows, Enter, Escape/Backspace and Home while focused. Clicking the display focuses it; it does not synthesize touchscreen coordinates. Use the TV remote buttons for mouse-operated navigation. QEMU's external window retains its own native mouse/keyboard input behavior.

Pause freezes guest execution; Resume continues the same VM. Remote injection is refused while paused. Stop terminates only the identity-checked managed VM, cancels its connection wait, and preserves the private disk. This is not a snapshot/revert feature. Existing debugger sessions should be detached before stopping their target.

The display stays local. It is not attached to AI messages or saved into projects. Live frames stay in memory; temporary fallback preview frames are removed after use. **Device Lab → Capture screen** is a separate explicit capture operation and saves its result in Studio's private per-user captures folder.

## Real devices

Enable Amazon Developer Mode and select USB or TCP/IP on the device itself. Studio does not change connection mode, bypass authorization, root devices, reset the shared ADB server or scan the network.

- **Find USB devices / Refresh devices** enumerates the dedicated bridge. Offline and unauthorized devices are listed but cannot receive commands. Guidance identifies authorization, cable, power and network checks.
- Connect an explicit Wi-Fi address, then **Save target** with a friendly name. USB serials may also be bookmarked. **Connect saved** reconnects that one Wi-Fi address or looks for that exact USB serial. Bookmarks live outside projects; no keys or credentials are stored in them.
- **Inspect target** reads bridge state, OS/CPU architecture, developer UID, data-disk space and package-service availability. Results stay in the local output console.
- **Reconnect Wi-Fi** disconnects/reconnects only the selected network target. USB mode and other connected targets remain unchanged.
- Install/run reports installation separately from the app reaching VISIBLE lifecycle state. Temporary VPKG uploads use unique names and are cleaned up without removing installed app data.

Physical Wi-Fi inspection and a synthetic file-transfer round trip were checked on Fire TV Stick 4K Select. Physical USB transport has not been qualified on connected hardware for this release. Enumeration and unauthorized-target behavior have regression coverage; neither establishes USB driver compatibility.

## IDE navigation

| Shortcut | Action |
| --- | --- |
| Ctrl+Shift+P | Filter and run available commands |
| Ctrl+P | Fuzzy file picker for the current project |
| Ctrl+G | Go to a line in the current editor |
| Ctrl+H | Replace text in the current file, with case/whole-word options |
| Ctrl+/ | Toggle line comments in supported source languages |
| Tab / Shift+Tab | Indent/outdent selected lines |
| Ctrl+Shift+B | Build the project |
| Ctrl+F5 | Build, install and run |
| Ctrl+Shift+E | Show the emulator panel |
| Ctrl+Shift+A | Show the coding assistant |

Quick open excludes generated/private directories and does not follow directory links. Replacement, comment and indentation edits stay unsaved until you save; each operation can be undone as one edit. These are local editor tools, not a language server, refactoring engine or semantic type checker.

QEMU references: [QMP control](https://www.qemu.org/docs/master/interop/qemu-qmp-ref.html), [GTK display options](https://www.qemu.org/docs/master/system/invocation.html).
