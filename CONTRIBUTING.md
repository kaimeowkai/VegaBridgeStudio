# Contributing

This preview is prepared for owner review before GitHub publication. Use Python 3.12+ on Windows and install the `dev` extra. Run `python -m pytest -q` and `python run_studio.py --smoke-test` before submitting a change.

Keep the Windows build path independent of Linux, WSL and Docker. Do not mark an emulator, USB transport or native compilation path supported until it has an actual test receipt. New AI integrations must never reuse credentials from another application and must keep file context explicit. Keep device operations cancellable and scoped to the selected target. Do not kill shared ADB servers or reset devices in tests.

Do not commit vendor SDK binaries/source, runtime images, credentials, signing identities, node_modules, generated packages or private device data. Add focused tests for behavior changes rather than mirroring the implementation.
