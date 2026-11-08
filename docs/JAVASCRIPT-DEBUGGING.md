# JavaScript debugging in the installed Vega app

The JavaScript debugger connects to the app's actual Hermes runtime through a loopback Metro inspector endpoint. The source preview is an editor view of original project files; the app itself runs in Vega. This release qualifies SDK 2.0.13986 / React Native 0.83 on the x86_64 Vega VM.

## Build, attach and step

1. Configure Windows Node/npm and the developer bridge, open a trusted project, and select its online local USB/TCP target. Stop a previous debugger before switching projects.
2. Open **JavaScript debugger** and choose **Build + run development app**. This saves source, builds a separate `-debug.vpkg`, starts a Studio-owned Metro child on loopback, installs and relaunches the project app, and verifies its visible lifecycle state. It preserves the release VPKG and uses the same project signing identity. Build/install can change the selected test app, so preserve valuable app data through your normal development workflow.
3. The host port defaults to 8081; an occupied host port selects a free local port. Only the selected device's app port 8081 is mapped to it. A conflicting existing device mapping is refused. Studio never stops another process to free a port.
4. Click **Attach JavaScript debugger**. Exactly one Metro target must match the project app ID. Its running script must match the served bundle; mapped source content must match the project files. A stale or ambiguous target is refused so a breakpoint cannot silently refer to unrelated code.
5. Open a `.js`, `.jsx`, `.ts` or `.tsx` source file in **Code**. Use **F9** or the gutter to set a breakpoint, then trigger that code in the app or evaluate a trusted expression in the debugger's Console. Unmapped lines remain unverified.
6. Inspect the original source, stack and locals. **F10** steps over, **F11** steps into, **Shift+F11** steps out, and **F5** continues. Evaluation while paused uses the selected frame. Expanding properties does not automatically invoke getters. The console executes in your test app and can change its state.
7. **Detach; keep app running** resumes the app and disconnects the inspector. **Stop owned Metro** separately stops only Studio's child, removes only its owned reverse mapping, and clears this component's debug-launch overrides. Relaunch normally after testing to use normal lifecycle timeouts. A disconnected target produces an explicit restore command instead of silently claiming cleanup succeeded.

Development launch uses Amazon's per-component `--disable-app-timeout` setting before launching, because a paused app cannot send heartbeat signals. This is scoped to the current project's component and does not alter global device security. Do not combine it with separately managed debugger launch overrides: cleanup uses `vlcm debug <component-id> --clear`. Closing Studio also cleans up its owned Metro session. An abnormal process exit can require that same explicit clear command after reconnecting.

## Editing and limitations

Rebuild and relaunch after source changes. Metro hot reload and inspector reconnect after a reload are not qualified here. A lost connection requires detach and re-attach; stale source maps are refused. Project changes and builds are guarded while an inspector session is active. The release build path keeps development mode disabled.

The actual GUI check set a breakpoint in an original `index.js`, evaluated a calculation with seed 7, saw `before = 12`, stepped to `answer = 24`, continued and detached. Native attachment to that same installed app was also checked separately. Synthetic test source is used in the public screenshot; no personal conversation or account credential is included.

This is a focused CDP source debugger, not the complete React Native DevTools application. The SDK may print an unsupported-client informational message. React component inspection, profiling, platform services, ARM target attachment and USB driver compatibility need their respective official tools or separate qualification. Release-specific results are recorded in [verification](VERIFICATION.json).
