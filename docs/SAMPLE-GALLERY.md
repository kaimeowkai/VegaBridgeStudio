# Original sample gallery

All 20 samples were built on Windows, installed into the real Vega virtual device and checked for visible UI and remote interaction. These images are actual emulator captures, not design mockups. They contain synthetic sample data.

Choose a template in New project, or open its standalone source under `examples/`. Set a unique package ID before publishing your own app. Install pinned dependencies through Build package. Private state and signing identities are created locally and are not included.

| Sample | Purpose | Emulator view |
| --- | --- | --- |
| [Focus Harbor TV](../examples/focus-harbor/) | Work and break timers with persistent sessions, pause/resume and a completed-session count. | <img src="screenshots/01-focus-harbor.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Room Rounds](../examples/room-rounds/) | Rotate household tasks across people and track completed rounds. | <img src="screenshots/02-room-rounds.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Measure Mosaic](../examples/measure-mosaic/) | Convert distances and temperatures with a remote-controlled value pad. | <img src="screenshots/03-measure-mosaic.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Signal Bench](../examples/signal-bench/) | Inspect screen metrics and monitor real TV remote input events. | <img src="screenshots/04-signal-bench.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Pantry Orbit](../examples/pantry-orbit/) | Build a weekly meal rotation from an editable pantry shortlist. | <img src="screenshots/05-pantry-orbit.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Agenda Arc](../examples/agenda-arc/) | Plan a week using editable daily focus cards. | <img src="screenshots/06-agenda-arc.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Split Ledger](../examples/split-ledger/) | Calculate a shared bill with adjustable tip and group size. | <img src="screenshots/07-split-ledger.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Quiet Intervals](../examples/quiet-intervals/) | An adjustable visual pacing loop with a pause control. | <img src="screenshots/08-quiet-intervals.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Palette Dock](../examples/palette-dock/) | Explore color pairs and calculate their actual WCAG contrast ratio. | <img src="screenshots/09-palette-dock.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Story Sparks](../examples/story-sparks/) | Generate and save original writing prompts from combinatorial story ingredients. | <img src="screenshots/10-story-sparks.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Decision Dock](../examples/decision-dock/) | Create options, collect local votes and see a tie-aware result. | <img src="screenshots/11-decision-dock.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Packing Lantern](../examples/packing-lantern/) | Create a reusable packing checklist and track packed items. | <img src="screenshots/12-packing-lantern.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Tempo Tiles](../examples/tempo-tiles/) | A visual metronome with tempo and beat-group controls. | <img src="screenshots/13-tempo-tiles.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Session Canvas](../examples/session-canvas/) | Write cue cards and present them as a full-screen TV sequence. | <img src="screenshots/14-session-canvas.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Word Garden](../examples/word-garden/) | Arrange letter tiles to uncover locally generated word clues. | <img src="screenshots/15-word-garden.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Ember Courier](../examples/ember-courier/) | Deliver sparks to four corner beacons while managing heat and cooling tiles. | <img src="screenshots/16-ember-courier.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Orbit Orchard](../examples/orbit-orchard/) | Plant drifting fruit in columns; predict the next wind before harvesting groups. | <img src="screenshots/17-orbit-orchard.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Beacon Weave](../examples/beacon-weave/) | Weave a target light pattern using diagonal toggle stitches. | <img src="screenshots/18-beacon-weave.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Echo Atlas](../examples/echo-atlas/) | Recall a growing glyph route while its map rotates between rounds. | <img src="screenshots/19-echo-atlas.png" width="280" alt="Actual Vega emulator screenshot"> |
| [Tide Parcel](../examples/tide-parcel/) | Navigate three changing tide lanes, collect parcels and save anchors for storms. | <img src="screenshots/20-tide-parcel.png" width="280" alt="Actual Vega emulator screenshot"> |

## Game progression checked

Ember Courier completed a 17-step, four-beacon route at heat 5/9. Orbit Orchard completed its 20-turn season with 54 points. Beacon Weave reached the target pattern in six stitches. Echo Atlas completed two memory routes, handled a wrong glyph, and replayed a route. Tide Parcel completed 18 tides with 13 parcels, full hull and one anchor remaining. These are functional developer checks, not a claim of exhaustive gameplay QA.

## Scope

The sample apps work offline and use original code-drawn illustrations. Common mechanics may resemble other software; no existing game characters, branding or copied artwork are included. The gallery targets TV remote navigation. The emulator’s system keyboard can differ from a physical device; PC text injection was also tested. Media playback, IAP, DRM and hardware peripherals are separate qualification work.
