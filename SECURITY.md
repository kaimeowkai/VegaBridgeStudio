# Security and privacy

Do not attach API keys, `.env` files, signing material, private app logs or personal device screenshots to public issues. Use a minimal sanitized reproduction. During this local review there is no public repository or configured private vulnerability-report address; contact the project owner privately before disclosing a sensitive issue.

The app encrypts API keys and newly generated development signing keys with Windows CurrentUser DPAPI. It does not read ChatGPT/Codex login stores. The assistant is text-only and cannot execute suggested commands. Context attachment blocks generated/private folders and common credential patterns; this check is not a substitute for reviewing the preview.

The device shell and npm build commands run with the user's local/device privileges. Build trusted projects only. The bridge listens using the installed platform-tools' own defaults; this application uses its own server port and does not deliberately expose a bridge over the network. Remote VVD uses existing SSH keys and strict host-key checking. No root access, DRM bypass, automatic firmware updates or device reset is provided.

Publication checks must inspect both the allowlisted source archive and binary distribution for secrets, internal SDK files, user data and unexpected files. Never include the local SDK analysis directory or QA workspace. Only dependency license files are collected from the build environment.
