# Checking and installing updates

Open **Help → Check for updates** to check the public [VegaBridge Studio releases](https://github.com/kaimeowkai/VegaBridgeStudio/releases), read release notes, download a newer Windows package, or restart into a verified update.

In **Settings → Updates**:

- **Check for updates automatically** checks at startup, at most once every eight hours. No GitHub sign-in is needed. The request contains the app version in its User-Agent; no chats, project source, account tokens or API keys are sent.
- **Download verified updates automatically and install on the next clean exit** enables automatic installation. Studio prepares the update in the background and waits for you to exit normally. It never forces a restart while you are working. The explicit Restart button refuses active builds, debugger sessions and managed-VM jobs.
- **Preview** includes community previews such as the current 0.x releases. **Stable** excludes releases marked as prereleases. Version comparisons prevent downgrades.

Automatic checks are enabled by default; automatic downloads/installations are opt-in. Source checkouts can check releases but use Git to update their source. The complete portable Windows package supports installation through the separate `VegaBridgeUpdater.exe` worker.

## What is verified

The updater only discovers releases from `kaimeowkai/VegaBridgeStudio`. It requires the expected Windows ZIP, a GitHub SHA-256 asset digest and a matching `SHA256SUMS.txt` entry. HTTPS downloads may redirect only to the permitted GitHub asset hosts. Downloads have size limits, and archives reject path escapes, Windows reserved names, links and duplicate paths.

The staged application must match every file hash in its installation manifest and the selected release version. This checks integrity against the public GitHub release; it is not an Authenticode signature or an independent publisher-signing scheme. The community Windows binaries remain unsigned.

Keep projects outside the extracted `VegaBridgeStudio` application folder. If added files or links appear inside that folder, automatic replacement is refused so unrelated work is not silently moved or overwritten. Encrypted chats, credentials, preferences, captures and connection bookmarks already live in the per-user data folder outside the installation.

## Installation and rollback

The worker is copied outside the application folder, waits for the exact Studio executable to exit, re-verifies both installations, and renames the folders. The old installation is retained beside the new one as `VegaBridgeStudio.previous-<unique ID>`. A failed replacement rename restores the old folder. Updates do not request administrator privileges or delete old installations.

To return to the old version, close Studio and launch its executable from the retained previous folder, or move that folder back after moving the new installation aside. Your per-user data remains separate. Update receipts are saved under the private per-user `updates` directory. You can also keep using the separately versioned GitHub ZIP downloads.
