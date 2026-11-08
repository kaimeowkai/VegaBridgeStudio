# Android to Vega migration methodology

This is an unreleased source prototype. VegaBridge Studio 0.4.0's downloaded executables do not yet include the assessor or compatibility workbench.

## Two reusable development tracks

The goal is shared automation rather than a sequence of hand-written app ports. The **conversion track** will use one versioned API/adapter registry and repeatable translation/behavior tests across projects. The **runtime track** investigates an Android environment that could accept unchanged APKs. Current functionality covers assessment, mapping review, preservation and runtime observations. Neither an automatic converter engine nor an Android runtime is implemented yet. See [runtime research and actual evidence](ANDROID-RUNTIME-RESEARCH.md).

## GUI import and adapter review

Run Studio from the source checkout, then choose **Tools → Import Android app for compatibility planning**.

1. Select a source folder or APK and a **new planning workspace outside the input**. The workflow never opens the Android project as an editable Vega project.
2. Click **Assess input and verify preservation**. A SHA-256 inventory before and after the scan checks original files, including source, assets and configuration. Generated/VCS directories are explicitly excluded; linked paths are inventoried without following them. Unreadable inputs stop the preservation gate.
3. Review **Shared adapters**. Each detected feature gets a shared-registry mapping choice, evidence paths, notes and an Unreviewed/Plan reviewed/Blocked state. Reviewing a plan never marks its implementation as tested.
4. Optionally use **Runtime research** to inspect a selected local Vega target. The probe reads device-node visibility and shell facts; it does not install software, mount filesystems or change permissions. Developer-shell observations do not establish production app capabilities.
5. Click **Create planning workspace**. Studio rechecks the original, writes separate reports and verifies the original again. Existing output folders, overlapping paths and source changes are refused. There is no conversion action in this workflow.

The new workspace contains assessment, adapter-map, source-baseline, plan, runtime-research, preservation-receipt and workspace files. It contains no copied source, APK or signing key. These are local planning records; source paths and evidence filenames can identify your project. To revise a plan in this prototype, reassess and save to another new workspace; in-place plan editing/reopening is not implemented.

## What can run, and what can be reused

VegaBridge already sideloads signed Vega `.vpkg` packages through Developer Mode. Amazon documents that package format for device installation. An Android APK cannot be made compatible by changing its extension: Vega has no Android ART or Activity framework. The shared Linux foundation is useful for some portable code, but does not supply the Android app runtime. [Amazon's runtime explanation](https://developer.amazon.com/apps-and-games/blogs/2026/10/port-your-tv-app-to-react-native-with-adbt), [package installation](https://developer.amazon.com/docs/vega/latest/app-management-com-tools).

The practical goal is a repeatable source migration pipeline. Amazon also documents an AI-assisted App Porting workflow for React Native, native Java/Kotlin and WebView projects. That provides a reference workflow; this prototype does not install, copy or integrate that tool. [Official migration paths](https://www.developer.amazon.com/docs/adbt/port-fire-os-app-to-vega).

| Input | Reuse opportunity | Work to prove |
| --- | --- | --- |
| React Native JS/TS | Application logic and compatible UI source | Pin Vega's runtime version; inspect every native dependency and TV input path |
| HTML/CSS/JS | Web content where Vega WebView is appropriate | Replace Android bridges, qualify playback/storage and preserve remote navigation |
| Portable C/C++ | Algorithms, parsers and protocol implementations | Rebuild for the Vega ABI/toolchain; replace JNI, NDK or Android service dependencies |
| Java/Kotlin | Behavior, data models, algorithms and tests | Translate selected logic with equivalent tests; rebuild platform UI/services |
| APK only | Package structure, declared permissions when readable, DEX/native inventory | Obtain source or do a separate reconstruction investigation; inventory is not executable conversion |

Amazon explicitly distinguishes portable standard C/C++ and JS libraries from platform-dependent native implementations. A matching CPU architecture alone does not qualify an Android `.so` for Vega. [Library portability guidance](https://developer.amazon.com/docs/vega-api/2.0/porting-libraries).

## The pipeline to build into Studio

1. **Capture the app's behavior.** List every screen, feature, network protocol, data format and lifecycle transition. Save representative inputs and expected outputs. Keep the original project untouched and give Vega output its own directory.
2. **Assess dependencies.** Classify the project and inventory dependencies, Android APIs, native libraries and permissions. For each feature, record a reuse candidate, an adapter to implement, or an unresolved dependency. Avoid a guessed compatibility percentage.
3. **Extract a platform-neutral core.** Keep calculations and protocols separate from UI, storage and hardware. Preserve existing tests; create golden vectors before translating Java/Kotlin logic. Recompile eligible native code rather than copying Android binaries.
4. **Implement explicit adapters.** Use small interfaces for storage, playback, billing/entitlements, connectivity and lifecycle. Verify exact API availability against the selected Vega SDK. Unsupported features remain visible in an unresolved-work list; do not replace them with silent no-ops.
5. **Build one complete slice.** Start the app, navigate by remote, perform the main action, save state and reopen it. Compare observable behavior with the original. This proves the approach before attempting a whole-app migration.
6. **Build and sideload a VPKG.** Use the existing VegaBridge build/sign/install/run path and selected emulator. Verify architecture, launch, focus, Back, persistence and errors. Media, purchases and hardware services need their own qualification before claiming parity.

An Android compatibility runtime would be a separate research project: ART/framework support, Android IPC and services, graphics/input integration and native ABI compatibility. Embedding an Android guest is another separate architecture with substantial resource and integration costs. Neither capability exists in this assessor or in the current VegaBridge release.

## Try the read-only assessor from source

From the VegaBridge source checkout:

```powershell
.\.venv\Scripts\python.exe -X utf8 run_cli.py --json assess-android "C:\Projects\AndroidApp" --plan "C:\MigrationReports\AndroidApp.md"
.\.venv\Scripts\python.exe -X utf8 run_cli.py --json assess-android "C:\Packages\example.apk"
```

The command returns local JSON. `--plan` creates a new Markdown report outside the input project and refuses to overwrite an existing file. It does not build, install dependencies, contact an AI provider, alter signing keys, extract APK contents or send anything to a device.

Source inspection reads bounded text files, Gradle dependency literals and version catalogs, and package dependency names. It skips generated/private directories and linked paths. Reports include relative evidence paths and dependency names, never full source text or dependency URLs. APK inspection reports package entries, DEX counts, native ABI names and plain XML permissions; compiled binary manifests are explicitly marked undecoded. It does not decompile DEX or validate APK signature trust.

The scanner uses lexical indicators, so comments and unused dependencies can create findings, and indirect calls can be missed. Logic candidates merely lack recognized Android markers. Flavor manifests are inventoried together, not resolved as a Gradle build variant. File limits, unreadable text and directory failures are reported. A report with no findings is not proof that an app is portable.

## Next implementation milestone

Add a GUI assessment/review panel, then a versioned adapter registry and paired behavior-test harness. Only after those work should Studio generate a separate Vega scaffold and offer migration edits. The first conversion experiment should exercise one small calculation-and-storage feature before tackling media, purchases or hardware integration.
