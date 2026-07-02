"""ADE-exported Spectre netlist parsing, editing and op-point running.

Handles the Virtuoso netlister format:
  - `\\` line continuations
  - parameter values wrapped in parens: w=(1u) m=(8)
  - subckt hierarchy; instance paths are expanded so op points can be
    saved per hierarchical device (I0.NM14)
  - `// Library name:` / `// Cell name:` comments preceding each subckt
    (kept so sizes can be pushed back to the schematic)

Editing a device rewrites w/l (and scales the layout-derived as/ad/ps/pd/
nrd/nrs params) in the subckt master, i.e. all instances of that subckt
change together — same semantics as editing the schematic.
"""
import glob
import os
import re
import shutil
import subprocess

from . import config
from .psf import read_psfascii

_NUM_SUFFIX = {"T": 1e12, "G": 1e9, "M": 1e6, "K": 1e3, "k": 1e3,
               "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15,
               "a": 1e-18}


def parse_num(tok):
    """Spectre numeric literal (possibly '(1u)') -> float, or None."""
    tok = tok.strip()
    if tok.startswith("(") and tok.endswith(")"):
        tok = tok[1:-1].strip()
    m = re.match(r"^([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"
                 r"([TGMKkmunpfa]?)$", tok)
    if not m:
        return None
    return float(m.group(1)) * (_NUM_SUFFIX.get(m.group(2), 1.0)
                                if m.group(2) else 1.0)


def fmt_num(v):
    """float -> spectre literal with engineering suffix."""
    for s, mul in [("", 1), ("m", 1e-3), ("u", 1e-6), ("n", 1e-9),
                   ("p", 1e-12), ("f", 1e-15)]:
        if abs(v) >= mul * 0.9999 or mul == 1e-15:
            return "%.5g%s" % (v / mul, s)
    return "%g" % v


class Instance:
    def __init__(self, name, nodes, master, params, subckt):
        self.name = name          # e.g. NM14
        self.nodes = nodes
        self.master = master      # primitive model or subckt name
        self.params = params      # dict param -> raw string token
        self.subckt = subckt      # subckt name it lives in, or None (top)

    def num(self, key, default=None):
        v = self.params.get(key)
        if v is None:
            return default
        n = parse_num(v)
        return default if n is None else n


class Netlist:
    def __init__(self, path):
        self.path = path
        with open(path) as f:
            self.rawlines = f.read().splitlines()
        # join continuations into logical lines, remember source spans
        self.logical = []          # (text, first_rawline_idx, n_rawlines)
        i = 0
        while i < len(self.rawlines):
            j = i
            text = self.rawlines[i]
            while text.rstrip().endswith("\\"):
                text = text.rstrip()[:-1] + " "
                j += 1
                text += self.rawlines[j].strip()
            self.logical.append((text, i, j - i + 1))
            i = j + 1
        self._parse()

    def _parse(self):
        self.subckts = {}          # name -> {cellinfo, instances{name: Instance}}
        self.top_instances = {}
        cur = None                 # current subckt name
        pend_lib = pend_cell = None
        for text, li, nl in self.logical:
            s = text.strip()
            m = re.match(r"//\s*Library name:\s*(\S+)", s)
            if m:
                pend_lib = m.group(1)
                continue
            m = re.match(r"//\s*Cell name:\s*(\S+)", s)
            if m:
                pend_cell = m.group(1)
                continue
            if s.startswith("//") or not s:
                continue
            m = re.match(r"subckt\s+(\S+)\s+(.*)$", s)
            if m:
                cur = m.group(1)
                self.subckts[cur] = dict(lib=pend_lib, cell=pend_cell,
                                         ports=m.group(2).split(),
                                         instances={})
                pend_lib = pend_cell = None
                continue
            if re.match(r"ends\b", s):
                cur = None
                continue
            inst = self._parse_instance(s, li, cur)
            if inst is not None:
                if cur:
                    self.subckts[cur]["instances"][inst.name] = inst
                else:
                    self.top_instances[inst.name] = inst

    _KEYWORDS = {"simulator", "global", "include", "ahdl_include",
                 "parameters", "subckt", "ends", "model", "options",
                 "save", "ic", "nodeset", "real", "if", "section",
                 "library", "endlibrary", "statistics", "simulatorOptions",
                 "modelParameter", "element", "outputParameter",
                 "designParamVals", "primitive", "subcktParameter",
                 "saveOptions", "sens", "info"}

    def _parse_instance(self, s, li, cur):
        m = re.match(r"([A-Za-z_][\w.]*)\s*\(([^)]*)\)\s*(\S+)\s*(.*)$", s)
        if not m:
            return None
        name, nodes, master, rest = (m.group(1), m.group(2).split(),
                                     m.group(3), m.group(4))
        if name in self._KEYWORDS:
            return None
        params = {}
        for pm in re.finditer(r"([\w.]+)\s*=\s*(\([^)]*\)|\S+)", rest):
            params[pm.group(1)] = pm.group(2)
        inst = Instance(name, nodes, master, params, cur)
        inst._line = li
        return inst

    # ---------- hierarchical expansion ----------
    def expand_paths(self, model_filter=None):
        """[(path, Instance)] for all primitive instances, DFS from top."""
        out = []

        def walk(prefix, instances, depth=0):
            if depth > 12:
                return
            for inst in instances.values():
                if inst.master in self.subckts:
                    walk(prefix + inst.name + ".",
                         self.subckts[inst.master]["instances"], depth + 1)
                elif model_filter is None or inst.master in model_filter:
                    out.append((prefix + inst.name, inst))

        walk("", self.top_instances)
        return out

    # ---------- editing ----------
    _SCALE_W = ("as", "ad")        # scale proportionally with w
    _OFFSET_W = ("ps", "pd")       # add delta-w (2 sides of perimeter)
    _INV_W = ("nrd", "nrs")        # scale with 1/w

    def set_mos_size(self, inst, w=None, l=None, m=None, mname="m"):
        """Rewrite w/l/multiplier on an instance line; adjust derived
        layout params (as/ad/ps/pd/nrd/nrs follow the per-unit w)."""
        text, li, nl = None, inst._line, None
        for t, i, n in self.logical:
            if i == inst._line:
                text, nl = t, n
                break
        w_old = inst.num("w")

        def repl(key, val, add=False):
            nonlocal text
            fv = ("%d" % val) if key in ("m", "mr", "nf") else fmt_num(val)
            pat = re.compile(r"\b(%s)\s*=\s*(\([^)]*\)|\S+)" % re.escape(key))
            if pat.search(text):
                text = pat.sub("%s=%s" % (key, fv), text, count=1)
                inst.params[key] = fv
            elif add:
                text = text.rstrip() + " %s=%s" % (key, fv)
                inst.params[key] = fv

        if l is not None:
            repl("l", l)
        if m is not None:
            repl(mname, int(round(m)), add=True)
        if w is not None and w_old:
            repl("w", w)
            k = w / w_old
            for p in self._SCALE_W:
                v = inst.num(p)
                if v is not None:
                    repl(p, v * k)
            for p in self._OFFSET_W:
                v = inst.num(p)
                if v is not None:
                    repl(p, v + (w - w_old))
            for p in self._INV_W:
                v = inst.num(p)
                if v is not None:
                    repl(p, v / k)
        # write back over the original raw span
        self.rawlines[inst._line:inst._line + nl] = [text]
        self._reindex()

    def _reindex(self):
        text = "\n".join(self.rawlines) + "\n"
        self.rawlines = text.splitlines()
        self.logical = []
        i = 0
        while i < len(self.rawlines):
            j = i
            t = self.rawlines[i]
            while t.rstrip().endswith("\\"):
                t = t.rstrip()[:-1] + " "
                j += 1
                t += self.rawlines[j].strip()
            self.logical.append((t, i, j - i + 1))
            i = j + 1
        self._parse()

    def instance_by_name(self, subckt, name):
        if subckt:
            return self.subckts[subckt]["instances"].get(name)
        return self.top_instances.get(name)

    def save(self, path=None):
        with open(path or self.path, "w") as f:
            f.write("\n".join(self.rawlines) + "\n")


class DesignDir:
    """A working copy of an ADE netlist directory (input.scs + netlist)."""

    _CONTROL_KEEP = re.compile(
        r"^\s*(simulator\b|global\b|include\b|ahdl_include\b|parameters\b)")
    _INCLUDE = re.compile(r'^\s*include\s+"([^"]+)"\s*(?:section=(\S+))?')

    def __init__(self, src, workname="design", pdk=None, corner=None):
        """src: path to ADE netlist directory or its input.scs."""
        if os.path.isfile(src):
            src = os.path.dirname(src)
        self.src = src
        self.pdk = pdk
        self.corner = corner
        self.remap_log = []
        self.dir = os.path.join(config.WORK_DIR, workname)
        if os.path.exists(self.dir):
            shutil.rmtree(self.dir)
        shutil.copytree(src, self.dir)
        self.input_scs = os.path.join(self.dir, "input.scs")
        # maestro layout: input.scs pulls the design via include "netlist";
        # direct si export: design lines are inline in input.scs itself
        nlpath = os.path.join(self.dir, "netlist")
        self.inline_design = True
        if os.path.exists(nlpath) and os.path.exists(self.input_scs):
            body = open(self.input_scs, errors="ignore").read()
            if re.search(r'include\s+"netlist"', body):
                self.inline_design = False
        elif os.path.exists(nlpath):
            self.inline_design = False
        self.netlist = Netlist(self.input_scs if self.inline_design
                               else nlpath)

    def _pdk_sections(self):
        secs = set()
        if self.pdk and os.path.exists(self.pdk.model_lib):
            for ln in open(self.pdk.model_lib, errors="ignore"):
                m = re.match(r"\s*section\s+(\S+)", ln)
                if m:
                    secs.add(m.group(1))
        return secs

    def _full_section_set(self, corner):
        """Lib includes covering every device class at one corner."""
        out = ['include "%s" section=%s' % (self.pdk.model_lib, corner)]
        for m in (self.pdk.bjt_sections, self.pdk.res_sections,
                  self.pdk.cap_sections):
            if corner in m:
                out.append('include "%s" section=%s'
                           % (self.pdk.model_lib, m[corner]))
        return out

    def _remap_include(self, line, secs, corner):
        """Repair model includes: files from a removed PDK are retargeted
        to the active PDK's lib; a corner-lib included without section
        (broken ADE model setup) is expanded to all device-class sections.
        Returns a list of replacement lines."""
        m = self._INCLUDE.match(line)
        if not m:
            return [line]
        path, section = m.group(1), m.group(2)
        full = path if os.path.isabs(path) else os.path.join(self.dir, path)
        exists = os.path.exists(full)
        if exists and section:
            return [line]
        if exists and not section:
            if not path.endswith(".lib"):
                return [line]      # plain .scs/.ckt include - fine as is
            # a .lib without section never elaborates: expand it
            if not self.pdk:
                return [line]
            new = self._full_section_set(corner)
            self.remap_log.append("%s -> sections %s" % (line.strip(), corner))
            return new
        if not self.pdk:
            return ["// [gmid] missing include dropped: " + line.strip()]
        if section:
            if section in secs:
                new = 'include "%s" section=%s' % (self.pdk.model_lib, section)
                self.remap_log.append("%s -> %s" % (line.strip(), new))
                return [new]
            self.remap_log.append("dropped (no section %s): %s"
                                  % (section, line.strip()))
            return ["// [gmid] missing include dropped: " + line.strip()]
        # sectionless model .ckt/.mdl files: the remapped lib sections
        # already pull these in — including them again redefines models
        self.remap_log.append("dropped: " + line.strip())
        return ["// [gmid] missing include dropped: " + line.strip()]

    def _default_bare_params(self, line):
        """ADE design variables can appear without a value in the point
        netlist (`parameters Vos CL=50f`); give them 0 so the op runs."""
        if not re.match(r"\s*parameters\b", line):
            return line
        toks = line.split()
        out = [toks[0]]
        for i, t in enumerate(toks[1:]):
            if "=" not in t:
                self.remap_log.append("bare parameter %s -> 0" % t)
                t = t + "=0"
            out.append(t)
        return " ".join(out)

    # statements that must not run in the op-only deck
    _STRIP = re.compile(
        r"^\s*(\w+\s+(tran|ac|noise|xf|stb|sp|pss|pac|pnoise|pxf|qpss|"
        r"envlp|sweep|montecarlo|checklimit|info)\b"
        r"|\w+\s+dc\b|save\b|saveOptions\b)")

    @staticmethod
    def _logical_lines(path):
        out = []
        raw = open(path).read().splitlines()
        i = 0
        while i < len(raw):
            j = i
            t = raw[i]
            while t.rstrip().endswith("\\"):
                t = t.rstrip()[:-1] + " "
                j += 1
                t += raw[j].strip()
            out.append(t)
            i = j + 1
        return out

    def op_deck(self, save_paths):
        """Build op-only deck: control/design from input.scs, with model
        includes repaired, analyses stripped and a single dc op added."""
        lines = []
        if os.path.exists(self.input_scs):
            for ln in self._logical_lines(self.input_scs):
                if self.inline_design:
                    # keep everything except analyses/saves
                    if not self._STRIP.match(ln):
                        lines.append(ln.rstrip())
                elif self._CONTROL_KEEP.match(ln):
                    lines.append(ln.rstrip())
        else:
            lines = ['simulator lang=spectre', 'global 0',
                     'include "netlist"']
        secs = self._pdk_sections()
        self.remap_log = []
        corner = self.corner or (self.pdk.default_corner if self.pdk else "tt")
        lines = [x for ln in lines
                 for x in self._remap_include(ln, secs, corner)]
        lines = [self._default_bare_params(ln) for ln in lines]
        # dedupe includes (remapping can fold several old libs into one)
        seen, out = set(), []
        for ln in lines:
            m = self._INCLUDE.match(ln)
            if m:
                key = (m.group(1), m.group(2))
                if key in seen:
                    self.remap_log.append("deduped: " + ln.strip())
                    continue
                seen.add(key)
            out.append(ln)
        lines = out
        deck = "\n".join(lines) + "\n"
        for p in save_paths:
            deck += ("save " + " ".join(
                "%s:%s" % (p, q) for q in
                ["ids", "gm", "gds", "gmbs", "vgs", "vds", "vbs",
                 "vth", "vdsat", "cgg", "cdd"]) + "\n")
        deck += "gmidop dc\n"
        return deck

    def run_op(self, save_paths):
        """Run a dc op; return {path: {param: float}}."""
        self.netlist.save()
        deck = self.op_deck(save_paths)
        deckfile = os.path.join(self.dir, "gmid_op.scs")
        with open(deckfile, "w") as f:
            f.write(deck)
        log = os.path.join(self.dir, "gmid_op.log")
        with open(log, "w") as lf:
            r = subprocess.run(
                [config.SPECTRE, "gmid_op.scs", "-format", "psfascii",
                 "-raw", "gmid_raw"],
                stdout=lf, stderr=subprocess.STDOUT, cwd=self.dir)
        if r.returncode != 0:
            raise RuntimeError("Spectre op failed:\n" +
                               open(log).read()[-2500:])
        op = read_psfascii(os.path.join(self.dir, "gmid_raw", "gmidop.dc"))
        out = {}
        for p in save_paths:
            d = {}
            for q in ["ids", "gm", "gds", "gmbs", "vgs", "vds", "vbs",
                      "vth", "vdsat", "cgg", "cdd"]:
                key = "%s:%s" % (p, q)
                if key in op:
                    d[q] = float(op[key][0])
            out[p] = d
        return out
