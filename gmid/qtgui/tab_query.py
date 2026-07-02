from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QComboBox,
                             QLineEdit, QPushButton, QLabel, QTableWidget,
                             QTableWidgetItem, QMessageBox)

from ..i18n import tr
from ..lut import MosLUT
from .common import parse_si, fmt_si

ROWS = [("vgs", "VGS", "V"), ("vth", "Vth", "V"), ("vdsat", "Vdsat", "V"),
        ("vov", "Vov", "V"), ("ids", "ID", "A"), ("gm", "gm", "S"),
        ("gds", "gds", "S"), ("gmbs", "gmb", "S"), ("gmid", "gm/ID", "1/V"),
        ("gain", "gm/gds", ""), ("ft", "fT", "Hz"), ("idw", "ID/W", "A/m"),
        ("cgg", "Cgg", "F"), ("cgs", "Cgs", "F"), ("cgd", "Cgd", "F"),
        ("cdd", "Cdd", "F")]


class QueryTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        top = QHBoxLayout()
        self.dev = QComboBox()
        self.dev.addItems(list(ctx.pdk().mos))
        self.L = QLineEdit("0.5")
        self.vds = QLineEdit("0.9")
        self.vsb = QLineEdit("0")
        for e in (self.L, self.vds, self.vsb):
            e.setMaximumWidth(70)
        self.mode = QComboBox()
        self.mode.addItem("gm/ID [1/V]", "gmid")
        self.mode.addItem("VGS [V]", "vgs")
        self.mode.addItem("Vov [V]", "vov")
        self.val = QLineEdit("15")
        self.val.setMaximumWidth(80)
        self.smode = QComboBox()
        self.smode.addItem(tr("none"), "")
        self.smode.addItem("gm [S]", "gm")
        self.smode.addItem("ID [A]", "ids")
        self.sval = QLineEdit()
        self.sval.setPlaceholderText("1m / 100u")
        self.sval.setMaximumWidth(90)
        btn = QPushButton(tr("query"))
        btn.clicked.connect(self.query)
        for w in [QLabel(tr("device")), self.dev, QLabel("L [µm]"), self.L,
                  QLabel("VDS"), self.vds, QLabel("VSB"), self.vsb,
                  QLabel(tr("given")), self.mode, self.val,
                  QLabel(tr("size_target")), self.smode, self.sval, btn]:
            top.addWidget(w)
        top.addStretch(1)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([tr("parameter"), tr("value")])
        self.table.horizontalHeader().setStretchLastSection(True)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)

    def query(self):
        try:
            lut = MosLUT.get(self.dev.currentText(), self.ctx.corner(),
                             self.ctx.pdk())
            L = parse_si(self.L.text()) * 1e-6
            vds = parse_si(self.vds.text())
            vsb = parse_si(self.vsb.text(), 0.0)
            kw = {self.mode.currentData(): parse_si(self.val.text())}
            smode = self.smode.currentData()
            sval = parse_si(self.sval.text())
            if smode and sval:
                gmid = kw.get("gmid")
                if gmid is None:
                    gmid = lut.query(L, vsb, vds, **kw)["gmid"]
                r = lut.size_for(L, vsb, vds, gmid, **{smode: sval})
            else:
                r = lut.query(L, vsb, vds, **kw)
                r["W"] = None
        except Exception as e:
            QMessageBox.warning(self, tr("error"), str(e))
            return
        rows = list(ROWS)
        if r.get("W"):
            rows.append(("W", tr("W_computed"), "m"))
        self.table.setRowCount(len(rows))
        for i, (k, label, unit) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(label))
            self.table.setItem(i, 1, QTableWidgetItem(fmt_si(r.get(k), unit)))
        self.table.resizeColumnsToContents()
