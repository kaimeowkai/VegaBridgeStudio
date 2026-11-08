# Third-party components

Original VegaBridge code is MIT-licensed. Dependency and system-tool licenses are independent.

The Windows distribution includes Python (PSF license), PySide6/Qt (LGPLv3/GPLv3/commercial options; this distribution uses the open-source LGPL option with dynamically linked Qt libraries), Shiboken, cryptography (Apache/BSD), cffi/pycparser (MIT/BSD), zstandard (BSD), FlatBuffers (Apache 2.0), HTTPX/HTTP Core/AnyIO/H11/IDNA and their dependencies. Exact package versions and license files are collected into the binary ZIP's `licenses/` directory by the build script. Qt libraries remain separate in `_internal`; the review distribution does not prevent replacing them. Corresponding upstream sources are available from the links below. The original application source and build scripts accompany the review package.

- Python source: https://www.python.org/downloads/source/
- Qt/PySide source: https://download.qt.io/official_releases/QtForPython/pyside6/
- Qt source: https://download.qt.io/official_releases/qt/
- Qt LGPL information: https://www.qt.io/licensing/open-source-lgpl-obligations
- PyInstaller bootloader: https://pyinstaller.org/en/stable/license.html (GPL with bootloader exception)
- Other bundled dependency source links and license text: generated `licenses/` inventory.

Windows Node.js, Android platform-tools and any optional SDK/emulator are **external prerequisites** and not bundled. Amazon npm package declarations and a lockfile identify build dependencies; their code is downloaded by npm only when the user builds a project. No license to redistribute Amazon SDK files or images is asserted. Amazon, Vega, Fire TV, Android, ChatGPT and OpenAI names belong to their respective owners. No endorsement is implied.

Native debugging additionally uses an external CodeLLDB adapter (MIT) and its matching LLDB tools (LLVM Apache 2.0 with LLVM exceptions). API generation uses the owner's external SDK JAR, Windows JDK, Windows LLVM and Git for Windows shell. These tools, SDK bindings, and private compatibility copies are not included. See [CodeLLDB sources and notices](https://github.com/vadimcn/codelldb) and [LLVM licensing](https://llvm.org/docs/DeveloperPolicy.html#license).

VM window capture also includes windows-capture (MIT), NumPy (BSD and bundled library notices) and OpenCV Python (Apache 2.0 and bundled library notices). Capture is scoped to the QEMU child process launched by this Studio session and its exact window handle; no desktop monitor is captured. Their exact license files are in the generated license inventory.

Before public release, review the generated license inventory and confirm compliance for the exact build being published.
