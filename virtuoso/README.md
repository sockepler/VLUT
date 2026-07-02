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

   To auto-load, add that line to your `.cdsinit`. If you load it from a
   non-standard location, also `setenv VLUT_ROOT=/path/to/VLUT` so the
   plugin can find `vlut-cli`.

A **VLUT** menu appears in the CIW (`VLUT > gm/ID Sweep Sizing…`), or call
`VLUT()`.

## Form fields

| Field | Meaning |
|-------|---------|
| ADE netlist dir | directory holding the ADE-exported `input.scs` (the same one ADE ran). Get it from ADE: *Setup → Simulator → netlist dir*, or the maestro `…/netlist/` folder. |
| Corner | model-lib section to size against (must have a LUT) |
| Max unit W [um] | per-unit width cap; total W is split into `m` parallel units below it |
| Max iterations | gm/ID sizing loop cap per sweep point |
| Design variables | ADE design vars to override, e.g. `CL=2p Vcm=0.9` |
| Fixed targets | devices held at a fixed gm/ID, one group per line: `M3 M4 : 10 L=0.7` (L in µm, optional) |
| Sweep devices | device group whose gm/ID is swept, e.g. `M1 M2` |
| Sweep gm/ID values | the swept values, e.g. `8 12 16 20` |
| Sweep L [um] | optional L for the swept devices |
| Analysis | which result to evaluate the metric on (`ac`/`tran`/`dc`) |
| Metric | any ADE calculator expression, e.g. `gainBwProd(v("out"))`, `phaseMargin(v("out"))`, `ymax(db20(v("out")))`, `overshoot(v("out") …)` |
| Goal | maximize / minimize the metric |
| Waveform expr | expression plotted for the best point |

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
