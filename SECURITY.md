# Security and privacy

Report reproducible vulnerabilities privately to the repository owner. Do not include credentials, account records or personal transcripts in public issues.

Windows CurrentUser DPAPI protects app-owned OAuth sessions, API keys, development signing keys, saved conversations/drafts and assistant undo backups. These live outside projects. Studio does not read another application's login store. The source and portable-package export uses an explicit allowlist; personal state is excluded.

Workspace agent can read and edit source in the selected project, create new projects under the configured projects folder, build, install/run and control the selected developer device. It has no arbitrary shell tool or access to the private state directory. Source reads reject private/generated paths and common credential patterns; this heuristic cannot identify every private document. Select the correct project and trusted endpoint. File writes require a current hash, reject unsaved editor buffers and save a private encrypted undo record. Stop cancels pending work; operations already completed remain applied.

Discussion only has no tools. Responses and compatible API calls send the user's discussion and requested source to the configured endpoint. No chat history ships with the software. Tokens, authorization headers, OAuth callbacks and provider error bodies are omitted from task output. Device screenshots remain local.

Builds execute npm/project scripts under the user's Windows account. The manual device console executes with Developer Mode privileges. Use trusted projects. Studio uses its own configured ADB server port, strict SSH host-key checking for optional remote hosts, read-only source VM images and a separate writable overlay. It does not disable authentication, root devices, bypass DRM or modify firmware/security settings.

CMS signature verification checks mathematics and payload integrity, not certificate-chain trust or Amazon certification. Keep existing production signing identities. The preview's self-signed development identities are not Amazon-issued production credentials.
