# Native Windows onedir build. Windows' own ICU DLLs must resolve from System32.
# A similarly named MSYS/Git ICU DLL on PATH exports different (versioned) APIs.
from pathlib import Path
import re

root = Path(SPECPATH)
a = Analysis([str(root / 'run_studio.py')], pathex=[str(root)],
    binaries=[], datas=[(str(root / 'vegabridge/resources'), 'vegabridge/resources')],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest', 'capstone', 'elftools'], noarchive=False)
a.binaries = [item for item in a.binaries if not re.fullmatch(r'icu(?:uc|in|dt[0-9]+)\.dll', Path(item[0]).name, re.I)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='VegaBridgeStudio',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(root / 'vegabridge/resources/vegabridge.ico'), version=str(root / 'version-info.txt'))
cli_analysis = Analysis([str(root / 'run_cli.py')], pathex=[str(root)],
    binaries=[], datas=[(str(root / 'vegabridge/resources'), 'vegabridge/resources')],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest', 'capstone', 'elftools'], noarchive=False)
cli_analysis.binaries = [item for item in cli_analysis.binaries if not re.fullmatch(r'icu(?:uc|in|dt[0-9]+)\.dll', Path(item[0]).name, re.I)]
cli_pyz = PYZ(cli_analysis.pure)
cli_exe = EXE(cli_pyz, cli_analysis.scripts, [], exclude_binaries=True, name='VegaBridgeCLI',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True,
    icon=str(root / 'vegabridge/resources/vegabridge.ico'), version=str(root / 'version-info.txt'))
coll = COLLECT(exe, cli_exe, a.binaries, cli_analysis.binaries, a.datas, cli_analysis.datas,
    strip=False, upx=False, name='VegaBridgeStudio')
