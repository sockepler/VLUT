"""Shared Qt helpers: matplotlib canvas, background worker, SI formatting."""
import re
import traceback

from PyQt5.QtCore import QThread, pyqtSignal
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
from matplotlib.figure import Figure

_SI = {"T": 1e12, "G": 1e9, "M": 1e6, "k": 1e3, "K": 1e3,
       "m": 1e-3, "u": 1e-6, "µ": 1e-6, "n": 1e-9, "p": 1e-12,
       "f": 1e-15, "a": 1e-18}


def parse_si(s, default=None):
    if s is None:
        return default
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    if not s:
        return default
    m = re.match(r"^([-+0-9.eE]+)\s*([TGMkKmuµnpfa]?)", s)
    if not m:
        return default
    try:
        return float(m.group(1)) * (_SI.get(m.group(2), 1.0))
    except ValueError:
        return default


def fmt_si(v, unit=""):
    if v is None or v != v:
        return "—"
    if v == 0:
        return "0 " + unit if unit else "0"
    for s, p in [(1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""),
                 (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"),
                 (1e-15, "f")]:
        if abs(v) >= s * 0.9999:
            return "%.4g %s%s" % (v / s, p, unit)
    return "%.3e %s" % (v, unit)


class MplCanvas(FigureCanvasQTAgg):
    def __init__(self, width=7, height=5, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi,
                          tight_layout=True)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)

    def make_toolbar(self, parent):
        return NavigationToolbar2QT(self, parent)


class Worker(QThread):
    """Run fn(*args) off the GUI thread; signals result or error string."""
    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(object)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            self.done.emit(self._fn(*self._args, **self._kwargs))
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))
