# VLUT ADE plugin

Runs the VLUT gm/ID sweep-sizing loop from inside Virtuoso and evaluates
the result with real ADE/OCEAN calculator formulas.

## Install

1. Install VLUT (`./install.sh` in the repo root) so `venv/bin/vlut-cli`
   exists, and characterize the LUTs for your PDK.
2. Load the plugin in the CIW:

   ```
   load("/path/to/VLUT/virtuoso/vlut_ade.il")
   ```

   To **auto-load on every Virtuoso start**, run once:

   ```
   virtuoso/install_plugin.sh          # adds a guarded load to ~/.cdsinit
   virtuoso/install_plugin.sh --uninstall
   ```

   (`install.sh` already does this unless you pass `--no-plugin`.) The
   entry sets `VLUT_ROOT` and only loads if the file exists, so it never
   breaks Virtuoso startup. Restart Virtuoso, or `load(...)` once by hand
   for the current session.

A **VLUT** menu appears in the CIW with three items:
- **Netlist current ADE/Maestro into VLUT…** — one click: netlist the
  focused ADE Explorer/Assembler session and load it into the sweep form
  (`VLUTOpenFromADE()`)
- **gm/ID Sweep Sizing…** — the sweep-sizing form (`VLUT()`)
- **PDK / LUT Manager…** — switch PDK and characterize LUTs (`VLUTMgr()`)

## One-click from Maestro / ADE

With an ADE Explorer or Assembler session open, use the CIW menu item
above, or the **Netlist open ADE/Maestro → import** button on the form.
It runs `asiGetCurrentSession` → `asiNetlist` → `asiGetNetlistDir`, drops
the generated netlist directory into the form and scans it — no browsing.
(You can still **…or Browse netlist dir** to point at any saved netlist.)

## PDK / LUT Manager

- **PDK** cyclic — lists every `pdks/*.yaml`; selecting one shows its
  corners and, per device, which LUT corners are already built.
- **Characterize LUTs** — runs `vlut-cli char` in the background
  (`ipcBeginProcess`); progress prints to the CIW, the status view
  refreshes when done. Set devices / corner / temp / parallel jobs first.
- **Refresh status** — re-reads the inventory (use after adding a new
  `pdks/<name>.yaml` from the template, or after an external characterize).
- The main sizing form has a matching **PDK** selector; the chosen PDK is
  written into the sweep job so sizing uses that PDK's LUTs.

Adding a PDK needs no GUI: `cp pdks/example.yaml.template pdks/<name>.yaml`,
edit it, then **Refresh status** (or reload the plugin) — it appears in
both PDK selectors.

## Form fields

Nothing is free-typed except numbers and design-variable parameters:
the netlist directory comes from a file browser, and PDK / corner /
device / net / metric are all dropdowns or listboxes.

| Field | Input |
|-------|-------|
| ADE netlist dir | **Browse netlist dir…** button (native file chooser). Pick the folder holding the ADE `input.scs`. |
| Scan devices/nets | reads the netlist and fills the device listboxes and net dropdowns below |
| PDK | dropdown (every `pdks/*.yaml`) — sets the LUTs used |
| Corner | dropdown, populated from the selected PDK |
| Max unit W [um] | number — total W is split into `m` parallel units below this |
| Max iterations | number — sizing-loop cap per sweep point |
| Design variables | typed `A=1 CL=2p` (ADE design-variable overrides) |
| Sweep devices | **listbox** (multi-select) of scanned devices |
| Sweep gm/ID values | numbers, e.g. `8 12 16 20` |
| Sweep L [um] | number (0 = keep current L) |
| Fixed devices + gm/ID + L + **Add fixed group** | pick devices in the listbox, type gm/ID and L numbers, press Add — the group is appended to the read-only "Fixed groups" box (repeat for more groups; **Clear** resets) |
| Analysis | dropdown (`ac`/`tran`/`dc`) |
| Metric + on net | metric **type** dropdown (DC gain, phase margin, GBW, unity-gain freq, bandwidth, peak-to-peak, …) composed with a **net** dropdown → e.g. `phaseMargin(v("out"))` |
| Goal | maximize / minimize |
| Waveform | waveform **type** dropdown (magnitude dB / phase / voltage) on the chosen net, plotted for the best point |

The metric/waveform dropdowns cover the common cases; to use an exotic
formula, edit `VLUTMetricTypes` / `VLUTWaveTypes` at the top of
`vlut_ade.il` (one line each: `("label" "formula-with-%s-for-net")`).

## Buttons

- **Run sweep** — for each sweep value: copy the netlist, run the gm/ID
  sizing loop (Spectre OP → LUT resize → OP … until W converges, applying
  the design-variable overrides), then run the netlist's own analyses.
  Progress prints to the CIW. When done, the metric is evaluated on every
  point and the **Results** table is filled, with the best point marked.
- **Plot metric vs gm/ID** — opens a ViVA window with metric vs swept gm/ID.
- **Plot best waveform** — plots the *Waveform expr* of the best point in ViVA.
- **Apply best to schematic** — writes the best point's `w`/`l`/`m` back to
  the source schematics (uses the `// Library / Cell name` headers in the
  netlist; opens/saves each cellview).

## Notes

- The heavy lifting runs in a background `vlut-cli` process
  (`ipcBeginProcess`), so the CIW stays responsive during the sweep.
- Each sweep point gets its own working copy under
  `~/vlut_runs/sweep_<timestamp>/`; originals are never modified until you
  press *Apply*.
- The metric string is passed verbatim to `evalstring` after
  `selectResult`, so anything valid in the ADE calculator works.
- Symmetric devices sized independently can differ by <1 %; even them up
  by hand after Apply if exact matching is required.
```
