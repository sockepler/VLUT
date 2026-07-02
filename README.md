# VLUT — gm/id Design Tool (standalone GUI, EN/JA)

**VLUT** is a gm/id lookup-table analog design tool driven by a local
Cadence Spectre, inspired by [ADT](https://adt.master-micro.com/).
Desktop GUI (PyQt5), English / 日本語 UI.

**日本語の使用マニュアル: [docs/USAGE.ja.md](docs/USAGE.ja.md)**

## Setup & launch

```bash
./install.sh                                     # venv + deps + `vlut` on PATH
cp pdks/example.yaml.template pdks/my_pdk.yaml   # describe your PDK
vlut                                             # or ./start.sh
```

`install.sh` picks a Python ≥ 3.9, creates `venv/`, pip-installs the
package, and drops a `vlut` launcher into `~/.local/bin` (added to PATH
via `~/.bashrc` if needed). Requires Linux + X11, `spectre` in PATH, and
a Spectre corner-section model library from your PDK. Language, PDK and
corner are selected in the toolbar and persisted.

## Tabs

| Tab | Function |
|-----|----------|
| Curves | Plot any derived quantity vs any other (gm/ID, ID/W, gm/gds, fT, Vth, …), multiple L, VDS/VSB adjustable |
| Query / Size | Full op lookup at given gm/ID (or VGS/Vov); compute W from target gm or ID |
| **Netlist Designer** | Load an ADE-generated netlist, auto-detect PDK devices, run Spectre OP with the netlist's own biasing, enter per-device gm/ID (and L) targets, then iterate OP → LUT resize → OP … until W converges. W is split into m parallel units below a per-unit width cap. Save the sized netlist or push w/l/m back to the Virtuoso schematics via virtuoso-bridge |
| Topologies | Built-in CS stage / 5T OTA / two-stage Miller OTA: gm/id design + one-click Spectre AC verification (A0/GBW/PM + Bode) |
| Passives / BJT | Resistor measure/solve-L, MIM measure/solve-size, BJT VBE sweeps (IC/β) |
| Characterize | Generate MOS LUTs per device/corner/temp with parallel Spectre jobs |

## ADE plugin (in-Virtuoso sweep sizing)

`virtuoso/vlut_ade.il` embeds VLUT in the Virtuoso CIW. With an ADE
Explorer/Assembler (Maestro) session open, one menu click netlists the
current session and imports it (`asiNetlist` + `asiGetNetlistDir`) — no
manual browsing. Then set design variables + fixed/swept gm/ID targets in
the form, and for each swept value it resizes the netlist (op → LUT → op)
and runs the netlist's own ADE analyses. Any ADE/OCEAN calculator formula (`gainBwProd`, `phaseMargin`,
`ymax(db20(...))`, …) is the metric; results come back as a table with the
best point marked, a metric-vs-gm/ID ViVA plot, a best-point waveform plot,
and one-click push of the best `w/l/m` to the schematics. The headless
engine is `vlut-cli` (`scan` / `run job.json` / `apply`). See
[virtuoso/README.md](virtuoso/README.md).

## PDK support

PDKs are described by `pdks/<name>.yaml` — model lib path, corner
sections, MOS devices with sweep grids, BJT/resistor/cap device lists.
The desktop GUI can **create one for you**: the **＋ Add PDK** button in
the toolbar opens a dialog that browses to a Spectre model library,
auto-detects its corner sections and BSIM MOS models, and writes the
yaml — no hand-editing needed for the gm/id core. See
[pdks/example.yaml.template](pdks/example.yaml.template) for the format.
The descriptor files are gitignored: site-specific PDK data never leaves
your machine. Multiple PDKs can be installed side by side and switched
from the toolbar; LUTs are stored per PDK in
`luts/<pdk>_<dev>_<corner>.npz` (~1 min per device·corner to generate).

## Netlist Designer details

- Accepts both ADE layouts: maestro (`input.scs` + `include "netlist"`)
  and direct si export (design inline in input.scs). The directory is
  copied to `work/design/` — originals are never modified.
- Handles subckt hierarchy, `\` continuations, `w=(...)` parameter
  parens, `<model>_ckt` inline mismatch wrappers (`mr=` multiplier).
- Model includes pointing at removed/renamed PDK installs are
  auto-remapped to the active PDK (section-aware, deduplicated,
  section-less `.lib` includes expanded); see the remap log.
- Sizing edits the subckt master — all hierarchical occurrences change
  together, matching schematic semantics. `as/ad/ps/pd/nrd/nrs` follow
  the per-unit W; total W is split into m units below "Max unit W".
- Push-to-Virtuoso uses the `// Library name / Cell name` headers in
  the netlist to open each schematic and set instance `w`/`l`/`m`
  properties (requires virtuoso-bridge in local mode).

## Verified behaviour

LUT prediction vs Spectre (typical 0.18 µm process, tt, 27 °C):
5T OTA 40.5→40.3 dB, CS stage 38.0→37.9 dB, Miller OTA 77.6→77.8 dB with
PM 66→64°. Netlist iteration: a 7-device Miller OTA started from uniform
wrong sizes converges in 4 iterations with every gm/ID within 1 % of
target and unit widths within the configured cap.

## Layout

```
pdks/example.yaml.template   PDK descriptor template (real ones gitignored)
gmid/pdk.py                  PDK registry
gmid/char_mos.py             LUT characterization engine (parallel Spectre)
gmid/lut.py                  LUT interpolation / inverse lookup / sizing
gmid/netlist.py              ADE netlist parser/editor + op-deck builder
gmid/designer.py             netlist-driven gm/id iteration (W + multiplier)
gmid/topologies.py           built-in topology design procedures
gmid/verify.py               verification testbench generation
gmid/passives.py             R/MIM/BJT one-shot calculators
gmid/i18n.py                 EN/JA strings
gmid/qtgui/                  PyQt5 GUI (main + one module per tab)
```
