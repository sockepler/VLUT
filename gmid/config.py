"""Tool-level configuration (paths, simulator, characterization params).

PDK-specific definitions (devices, model libs, sweep grids) live in
pdks/*.yaml — see pdks/example.yaml.template.
"""
import os

TOOL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUT_DIR = os.path.join(TOOL_ROOT, "luts")
WORK_DIR = os.path.join(TOOL_ROOT, "work")

SPECTRE = "spectre"

DEFAULT_TEMP = 27.0

# op-point parameters saved during characterization (magnitudes stored)
MOS_PARAMS = ["ids", "vth", "vdsat", "gm", "gds", "gmbs",
              "cgg", "cgs", "cgd", "cgb", "cdd", "css"]

MAX_PARALLEL_SPECTRE = 4
