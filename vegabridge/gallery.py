"""Twenty original runnable starters, sharing a small TV UI foundation."""
import json
from pathlib import Path
import shutil

CATALOG = [
    ("focus-harbor", "Focus Harbor TV", "Productivity", "Work and break timers with persistent sessions, pause/resume and a completed-session count.", "FocusHarbor"),
    ("room-rounds", "Room Rounds", "Home", "Rotate household tasks across people and track completed rounds.", "RoomRounds"),
    ("measure-mosaic", "Measure Mosaic", "Utility", "Convert distances and temperatures with a remote-controlled value pad.", "MeasureMosaic"),
    ("signal-bench", "Signal Bench", "Developer", "Inspect screen metrics and monitor real TV remote input events.", "SignalBench"),
    ("pantry-orbit", "Pantry Orbit", "Home", "Build a weekly meal rotation from an editable pantry shortlist.", "PantryOrbit"),
    ("agenda-arc", "Agenda Arc", "Productivity", "Plan a week using editable daily focus cards.", "AgendaArc"),
    ("split-ledger", "Split Ledger", "Utility", "Calculate a shared bill with adjustable tip and group size.", "SplitLedger"),
    ("quiet-intervals", "Quiet Intervals", "Wellbeing", "An adjustable visual pacing loop with a pause control.", "QuietIntervals"),
    ("palette-dock", "Palette Dock", "Design", "Explore color pairs and calculate their actual WCAG contrast ratio.", "PaletteDock"),
    ("story-sparks", "Story Sparks", "Creative", "Generate and save original writing prompts from combinatorial story ingredients.", "StorySparks"),
    ("decision-dock", "Decision Dock", "Home", "Create options, collect local votes and see a tie-aware result.", "DecisionDock"),
    ("packing-lantern", "Packing Lantern", "Travel", "Create a reusable packing checklist and track packed items.", "PackingLantern"),
    ("tempo-tiles", "Tempo Tiles", "Music", "A visual metronome with tempo and beat-group controls.", "TempoTiles"),
    ("session-canvas", "Session Canvas", "Presentation", "Write cue cards and present them as a full-screen TV sequence.", "SessionCanvas"),
    ("word-garden", "Word Garden", "Learning", "Arrange letter tiles to uncover locally generated word clues.", "WordGarden"),
    ("ember-courier", "Ember Courier", "Game", "Deliver sparks to four corner beacons while managing heat and cooling tiles.", "EmberCourier"),
    ("orbit-orchard", "Orbit Orchard", "Game", "Plant drifting fruit in columns; predict the next wind before harvesting groups.", "OrbitOrchard"),
    ("beacon-weave", "Beacon Weave", "Game", "Weave a target light pattern using diagonal toggle stitches.", "BeaconWeave"),
    ("echo-atlas", "Echo Atlas", "Game", "Recall a growing glyph route while its map rotates between rounds.", "EchoAtlas"),
    ("tide-parcel", "Tide Parcel", "Game", "Navigate three changing tide lanes, collect parcels and save anchors for storms.", "TideParcel"),
]


def entries():
    return [dict(zip(["id", "title", "category", "description", "component"], row)) for row in CATALOG]


def install_template(root, template_id, identifier, language="JavaScript"):
    entry = next((e for e in entries() if e["id"] == template_id), None)
    if not entry:
        raise ValueError("Unknown gallery template")
    root = Path(root)
    source = root / "src"
    shutil.copytree(Path(__file__).parent / "resources/gallery", source, dirs_exist_ok=True)
    module = "games" if entry["category"] == "Game" else "apps"
    typed = language == "TypeScript"
    suffix = "tsx" if typed else "js"
    # Each generated project is standalone and editable, with its own package,
    # local save data, manifest and signing identity. No gallery app is downloaded.
    code = ("import React from 'react';\nimport {AppRegistry} from 'react-native';\n"
            "import {configureDesign} from './src/ui';\n"
            f"configureDesign('{template_id}');\n"
            f"import {{{entry['component']}}} from './src/{module}';\n"
            + ("const Starter: React.ComponentType = " if typed else "const Starter = ") + entry['component'] + ";\n"
            + f"AppRegistry.registerComponent('{identifier}.main', () => Starter);\n")
    (root / "index.js").unlink()
    (root / ("index." + suffix)).write_text(code, encoding="utf-8")
    pkg = json.loads((root / "package.json").read_text())
    pkg["scripts"]["bundle"] = pkg["scripts"]["bundle"].replace("--entry-file index.js", "--entry-file index." + suffix)
    (root / "package.json").write_text(json.dumps(pkg, indent=2), encoding="utf-8")
    if typed:
        (root / "tsconfig.json").write_text(json.dumps({"compilerOptions":{"allowJs":True,"checkJs":False,"jsx":"react-native","noEmit":True,"strict":True,"moduleResolution":"bundler","module":"esnext","target":"es2022","skipLibCheck":True,"esModuleInterop":True},"include":["index.tsx","src/**/*"]},indent=2))
    (root / "SAMPLE-INFO.json").write_text(json.dumps(entry | {"language":language,"source":"Original VegaBridge sample; common genre mechanics may have similarities to other software","requiresNetwork":False},indent=2),encoding="utf-8")
    make_icon(root / 'assets/image/hello.png', template_id)
    return entry


def make_icon(destination, seed, size=512):
    """Original geometric artwork; no external art, brands or icon fonts."""
    from .sample_art import draw_icon
    index=next((i for i,item in enumerate(CATALOG) if item[0]==seed),0)
    draw_icon(destination,index,size)
    return
