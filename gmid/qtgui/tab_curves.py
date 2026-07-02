from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QComboBox,
                             QLineEdit, QCheckBox, QPushButton, QLabel,
                             QGroupBox, QGridLayout, QMessageBox)

from ..i18n import tr
from ..lut import MosLUT, DERIVED
from .common import MplCanvas, parse_si


class CurvesTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx              # MainWindow (pdk(), corner())
        top = QHBoxLayout()
        self.dev = QComboBox()
        self.dev.addItems(list(ctx.pdk().mos))
        self.dev.currentTextChanged.connect(self._dev_changed)
        self.xsel = QComboBox()
        self.ysel = QComboBox()
        for k, (label, _) in DERIVED.items():
            self.xsel.addItem(label, k)
            self.ysel.addItem(label, k)
        self.xsel.setCurrentIndex(list(DERIVED).index("gmid"))
        self.ysel.setCurrentIndex(list(DERIVED).index("idw"))
        self.vds = QLineEdit("0.9")
        self.vds.setMaximumWidth(70)
        self.vsb = QLineEdit("0")
        self.vsb.setMaximumWidth(70)
        self.logx = QCheckBox(tr("log_x"))
        self.logy = QCheckBox(tr("log_y"))
        self.logy.setChecked(True)
        btn = QPushButton(tr("plot"))
        btn.clicked.connect(self.plot)
        for w in [QLabel(tr("device")), self.dev,
                  QLabel(tr("x_axis")), self.xsel,
                  QLabel(tr("y_axis")), self.ysel,
                  QLabel("VDS"), self.vds, QLabel("VSB"), self.vsb,
                  self.logx, self.logy, btn]:
            top.addWidget(w)
        top.addStretch(1)

        self.lbox = QGroupBox(tr("lengths"))
        self.lgrid = QGridLayout(self.lbox)
        self.lchecks = []
        self._dev_changed(self.dev.currentText())

        self.canvas = MplCanvas()
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.lbox)
        lay.addWidget(self.canvas.make_toolbar(self))
        lay.addWidget(self.canvas, 1)

    def _dev_changed(self, dev):
        for c in self.lchecks:
            c.setParent(None)
        self.lchecks = []
        d = self.ctx.pdk().mos.get(dev)
        if not d:
            return
        for i, L in enumerate(d["Ls"]):
            c = QCheckBox("%g" % L)
            c.setChecked(i % 3 == 0)
            self.lchecks.append(c)
            self.lgrid.addWidget(c, i // 12, i % 12)

    def plot(self):
        dev = self.dev.currentText()
        try:
            lut = MosLUT.get(dev, self.ctx.corner(), self.ctx.pdk())
        except FileNotFoundError as e:
            QMessageBox.warning(self, tr("error"), str(e))
            return
        vds = parse_si(self.vds.text(), 0.9)
        vsb = parse_si(self.vsb.text(), 0.0)
        xk = self.xsel.currentData()
        yk = self.ysel.currentData()
        ax = self.canvas.ax
        ax.clear()
        for c in self.lchecks:
            if not c.isChecked():
                continue
            L = float(c.text()) * 1e-6
            x, y = lut.curve(xk, yk, L, vsb, vds)
            ax.plot(x, y, label="L=%sµ" % c.text())
        ax.set_xlabel(DERIVED[xk][0])
        ax.set_ylabel(DERIVED[yk][0])
        if self.logx.isChecked():
            ax.set_xscale("log")
        if self.logy.isChecked():
            ax.set_yscale("log")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8)
        ax.set_title("%s @ %s, VDS=%g VSB=%g"
                     % (dev, self.ctx.corner(), vds, vsb), fontsize=10)
        self.canvas.draw_idle()
