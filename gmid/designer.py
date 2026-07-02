"""Netlist-driven gm/id iterative sizing.

Workflow:
  1. load an ADE netlist directory (DesignDir)
  2. scan for PDK devices; group MOS by (subckt, instance-name) — editing
     a subckt master resizes every hierarchical occurrence, matching
     schematic semantics
  3. run a Spectre dc op with the netlist's own biasing
  4. for each unlocked device compute W so that gm/ID hits its target at
     the simulated (ID, VDS, VSB); rewrite netlist; repeat until W settles
"""
import math

from . import pdk as pdkmod
from .netlist import DesignDir, fmt_num
from .lut import MosLUT


class MosItem:
    """One sizable device = one instance line in a subckt master."""

    def __init__(self, subckt, inst, paths):
        self.subckt = subckt          # subckt name or None (top level)
        self.name = inst.name
        self.master = inst.master     # as written: plain model or <model>_ckt
        self.model = (inst.master[:-4] if inst.master.endswith("_ckt")
                      else inst.master)   # LUT model name
        self.paths = paths            # hierarchical paths of occurrences
        self.w = inst.num("w")
        self.l = inst.num("l")
        self.nf = inst.num("nf", 1) or 1
        # plain device uses m=, the _ckt mismatch wrapper uses mr=
        self.mpar = "mr" if inst.master.endswith("_ckt") else "m"
        self.m = int(inst.num(self.mpar, 1) or 1)
        # design inputs
        self.target_gmid = None       # None = locked / untouched
        self.target_l = None          # None = keep current l
        # sim results (of first occurrence)
        self.op = {}

    @property
    def wtotal(self):
        return (self.w or 0) * self.nf * self.m

    def label(self):
        scope = self.subckt or "(top)"
        return "%s/%s" % (scope, self.name)


class NetlistDesign:
    def __init__(self, src, pdk=None, corner=None,
                 w_max=10e-6, w_min=0.5e-6):
        self.pdk = pdk or pdkmod.get()
        self.corner = corner or self.pdk.default_corner
        self.w_max = w_max            # per-unit W ceiling -> raises m
        self.w_min = w_min            # per-unit W floor   -> lowers m
        self.dd = DesignDir(src, pdk=self.pdk, corner=self.corner)
        self.log = []
        self._scan()

    def _scan(self):
        classes = self.pdk.all_models()
        nl = self.dd.netlist
        paths = nl.expand_paths(model_filter=set(classes))
        self.mos_items = []
        self.other_items = []       # (class, path, Instance)
        seen = {}
        for path, inst in paths:
            cls = classes[inst.master]
            if cls == "mos":
                key = (inst.subckt, inst.name)
                if key in seen:
                    seen[key].paths.append(path)
                else:
                    item = MosItem(inst.subckt, inst, [path])
                    seen[key] = item
                    self.mos_items.append(item)
            else:
                self.other_items.append((cls, path, inst))
        self.cellinfo = {name: (sc["lib"], sc["cell"])
                         for name, sc in nl.subckts.items()}

    # ---------- op ----------
    def run_op(self):
        paths = [it.paths[0] for it in self.mos_items]
        ops = self.dd.run_op(paths)
        for it in self.mos_items:
            raw = ops.get(it.paths[0], {})
            o = {k: abs(v) for k, v in raw.items()}
            ids = o.get("ids", 0.0)
            o["gmid"] = (o.get("gm", 0.0) / ids) if ids > 1e-12 else 0.0
            # vsb magnitude: nmos vbs<=0, pmos vbs>=0 in char convention
            o["vsb"] = abs(raw.get("vbs", 0.0))
            self_gain = o.get("gm", 0.0) / max(o.get("gds", 1e-30), 1e-30)
            o["gain"] = self_gain
            it.op = o
        return ops

    # ---------- sizing ----------
    def size_step(self, damping=1.0):
        """One resize pass from current op; returns max relative W change."""
        lut_cache = {}
        max_dw = 0.0
        for it in self.mos_items:
            if it.target_gmid is None or not it.op:
                continue
            ids = it.op.get("ids", 0.0)
            if ids < 1e-12:
                self.log.append("skip %s: off (ID=%.3g)" % (it.label(), ids))
                continue
            if it.model not in lut_cache:
                lut_cache[it.model] = MosLUT.get(it.model, self.corner,
                                                 self.pdk)
            lut = lut_cache[it.model]
            L = it.target_l or it.l
            vds = min(max(it.op.get("vds", lut.vmax / 2), 0.02), lut.vmax)
            vsb = min(it.op.get("vsb", 0.0), lut.VSB[-1])
            q = lut.query(L, vsb, vds, gmid=it.target_gmid)
            idw = q["ids"] / lut.W          # A per meter of W
            wtot_old = it.wtotal
            wtot_new = ids / max(idw, 1e-9)
            if damping != 1.0 and wtot_old:
                wtot_new = wtot_old * (wtot_new / wtot_old) ** damping
            # split into m parallel units so unit width stays reasonable
            m_new = max(1, math.ceil(wtot_new / (it.nf * self.w_max)))
            w_new = wtot_new / (it.nf * m_new)
            if w_new < self.w_min and m_new > 1:
                m_new = max(1, int(wtot_new / (it.nf * self.w_min)))
                w_new = wtot_new / (it.nf * m_new)
            w_new = max(w_new, 0.22e-6)
            dw = (abs(wtot_new - wtot_old) / wtot_old if wtot_old
                  else 1.0)
            max_dw = max(max_dw, dw)
            inst = self.dd.netlist.instance_by_name(it.subckt, it.name)
            self.dd.netlist.set_mos_size(inst, w=w_new, l=it.target_l,
                                         m=m_new, mname=it.mpar)
            it.w = w_new
            it.m = m_new
            if it.target_l:
                it.l = it.target_l
            self.log.append("%s: W %s x m=%d (Wtot %s, dW=%.1f%%)"
                            % (it.label(), fmt_num(w_new), m_new,
                               fmt_num(wtot_new), dw * 100))
        return max_dw

    def iterate(self, max_iter=8, tol=0.01, damping=1.0, callback=None):
        """Full loop: op -> resize -> op ... until W stable."""
        self.run_op()
        if callback:
            callback(0, None)
        for i in range(1, max_iter + 1):
            dw = self.size_step(damping=damping)
            self.run_op()
            if callback:
                callback(i, dw)
            if dw < tol:
                self.log.append("converged after %d iterations" % i)
                return True, i
        self.log.append("not converged (last dW=%.1f%%)" % (dw * 100))
        return False, max_iter

    def save_netlist(self, path):
        self.dd.netlist.save(path)

    # ---------- push to Virtuoso ----------
    def skill_for_push(self):
        """SKILL that writes current w/l back to the source schematics."""
        by_cell = {}
        for it in self.mos_items:
            info = self.cellinfo.get(it.subckt)
            if not info or not info[0]:
                continue
            by_cell.setdefault(info, []).append(it)
        lines = ["let((cv inst)"]
        for (lib, cell), items in by_cell.items():
            lines.append('cv = dbOpenCellViewByType("%s" "%s" "schematic" nil "a")'
                         % (lib, cell))
            for it in items:
                lines.append('inst = dbFindAnyInstByName(cv "%s")' % it.name)
                lines.append('when(inst '
                             'dbReplaceProp(inst "w" "string" "%.4gu") '
                             'dbReplaceProp(inst "l" "string" "%.4gu") '
                             'dbReplaceProp(inst "%s" "string" "%d"))'
                             % (it.w * 1e6, it.l * 1e6, it.mpar, it.m))
            lines.append("dbSave(cv)")
            lines.append("dbClose(cv)")
        lines.append("t)")
        return "\n".join(lines)
