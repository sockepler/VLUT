"""Add-PDK dialog: browse a model lib, auto-detect models/corners, write
a pdks/<name>.yaml — no hand-editing needed for the gm/id (MOS) core."""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QPushButton, QLabel, QFileDialog,
                             QTableWidget, QTableWidgetItem, QComboBox,
                             QCheckBox, QGroupBox, QGridLayout, QMessageBox,
                             QDialogButtonBox, QScrollArea, QWidget)

from .. import config
from ..pdkscan import scan_model_lib, mos_corner_sections, class_sections
from ..i18n import tr


class AddPdkDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("add_pdk"))
        self.resize(620, 520)
        self.scan = None

        # scrollable content; Save/Cancel stay pinned at the bottom
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(4, 4, 8, 4)

        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("my_pdk180  (file/id, no spaces)")
        self.title = QLineEdit()
        self.title.setPlaceholderText("My 0.18um PDK")
        librow = QHBoxLayout()
        self.lib = QLineEdit()
        self.lib.setReadOnly(True)
        b_browse = QPushButton(tr("browse"))
        b_browse.clicked.connect(self._browse_lib)
        librow.addWidget(self.lib, 1)
        librow.addWidget(b_browse)
        form.addRow(tr("pdk_name"), self.name)
        form.addRow(tr("pdk_title"), self.title)
        form.addRow(tr("model_lib"), librow)
        lay.addLayout(form)

        # corners
        self.cornerbox = QGroupBox(tr("mos_corners_pick"))
        self.cornergrid = QGridLayout(self.cornerbox)
        self.corner_checks = []
        lay.addWidget(self.cornerbox)

        # models
        lay.addWidget(QLabel(tr("mos_models_pick")))
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["✓", tr("col_model"), tr("polarity"), "Vmax [V]"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(150)
        lay.addWidget(self.table)

        # grid
        gbox = QGroupBox(tr("sweep_grid"))
        gf = QFormLayout(gbox)
        self.ls = QLineEdit("0.18 0.22 0.28 0.35 0.45 0.6 0.8 1.0 1.5 2.0 3.0 5.0")
        self.vsbs = QLineEdit("0 0.3 0.6 0.9")
        self.vgstep = QLineEdit("0.02")
        self.vdstep = QLineEdit("0.05")
        gf.addRow(tr("grid_ls"), self.ls)
        gf.addRow(tr("grid_vsbs"), self.vsbs)
        gf.addRow("VGS step [V]", self.vgstep)
        gf.addRow("VDS step [V]", self.vdstep)
        lay.addWidget(gbox)

        self.note = QLabel(tr("pdk_note"))
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color:#7a8aa5")
        lay.addWidget(self.note)
        lay.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)

    def _browse_lib(self):
        fn, _ = QFileDialog.getOpenFileName(
            self, tr("model_lib"), config.TOOL_ROOT,
            "Spectre model lib (*.lib *.scs *.mdl);;All files (*)")
        if not fn:
            return
        self.lib.setText(fn)
        try:
            self.scan = scan_model_lib(fn)
        except Exception as e:
            QMessageBox.warning(self, tr("error"), str(e))
            return
        self._populate()

    def _populate(self):
        mcorners = mos_corner_sections(self.scan["corners"])
        for c in self.corner_checks:
            c.setParent(None)
        self.corner_checks = []
        for i, c in enumerate(mcorners):
            chk = QCheckBox(c)
            chk.setChecked(c.lower() in ("tt", "ff", "ss"))
            self.corner_checks.append(chk)
            self.cornergrid.addWidget(chk, i // 6, i % 6)
        # models: skip inline _ckt wrappers (auto-handled in netlists)
        models = [(m, pol) for m, pol in self.scan["mos"]
                  if not m.endswith("_ckt")]
        self.table.setRowCount(len(models))
        for i, (m, pol) in enumerate(models):
            chk = QCheckBox()
            chk.setChecked("_dnw" not in m)
            cw = Q__center(chk)
            self.table.setCellWidget(i, 0, cw)
            self.table.setItem(i, 1, QTableWidgetItem(m))
            pc = QComboBox()
            pc.addItems(["n", "p"])
            pc.setCurrentText(pol)
            self.table.setCellWidget(i, 2, pc)
            vmax = "3.3" if "33" in m else "1.8"
            self.table.setItem(i, 3, QTableWidgetItem(vmax))
        self.table.resizeColumnsToContents()
        if not self.name.text():
            base = os.path.basename(self.lib.text()).split(".")[0]
            self.name.setText(base)

    def _save(self):
        name = self.name.text().strip().replace(" ", "_")
        if not name or not self.scan:
            QMessageBox.warning(self, tr("error"), tr("pdk_need_name_lib"))
            return
        corners = [c.text() for c in self.corner_checks if c.isChecked()]
        if not corners:
            QMessageBox.warning(self, tr("error"), tr("pdk_need_corner"))
            return
        # collect included models grouped by vmax
        rows = []
        for i in range(self.table.rowCount()):
            cw = self.table.cellWidget(i, 0)
            if not cw.findChild(QCheckBox).isChecked():
                continue
            m = self.table.item(i, 1).text()
            pol = self.table.cellWidget(i, 2).currentText()
            vmax = float(self.table.item(i, 3).text())
            rows.append((m, pol, vmax))
        if not rows:
            QMessageBox.warning(self, tr("error"), tr("pdk_need_model"))
            return
        Ls = self.ls.text().split()
        vsbs = self.vsbs.text().split()
        vgstep = float(self.vgstep.text())
        vdstep = float(self.vdstep.text())
        vmaxes = sorted(set(r[2] for r in rows))

        y = []
        y.append("name: %s" % name)
        y.append('title: "%s"' % (self.title.text().strip() or name))
        y.append('model_lib: %s' % self.lib.text())
        y.append("mos_corners: [%s]" % ", ".join(corners))
        y.append("default_corner: %s" % corners[0])
        y.append("default_temp: 27.0")
        y.append("grids:")
        for v in vmaxes:
            gname = "g%d" % round(v * 10)
            # IO/thick-oxide devices have a larger lmin; drop tiny Ls
            lmin = 0.35 if v >= 3.0 else 0.0
            gls = [x for x in Ls if float(x) >= lmin] or Ls
            y.append("  %s:" % gname)
            y.append("    vmax: %g" % v)
            y.append("    Ls: [%s]" % ", ".join(gls))
            y.append("    vsbs: [%s]" % ", ".join(vsbs))
            y.append("    vgs_step: %g" % vgstep)
            y.append("    vds_step: %g" % vdstep)
        y.append("mos:")
        for m, pol, vmax in rows:
            gname = "g%d" % round(vmax * 10)
            y.append('  %s: {polarity: %s, grid: %s, wchar: 10e-6}'
                     % (m, pol, gname))
        # optional device classes: only sections matching the chosen corners
        sel = set(c.lower() for c in corners)
        for cls, key in (("bjt", "bjt"), ("res", "res"), ("cap", "mim")):
            secs = class_sections(self.scan["corners"], key)
            secs = {k: v for k, v in secs.items() if k in sel}
            if secs:
                y.append("%s:" % cls)
                y.append("  section: {%s}" % ", ".join(
                    "%s: %s" % (k, v) for k, v in secs.items()))
                y.append("  devices: {}")
        text = "\n".join(y) + "\n"

        path = os.path.join(config.TOOL_ROOT, "pdks", name + ".yaml")
        if os.path.exists(path):
            if QMessageBox.question(
                    self, tr("add_pdk"),
                    "%s exists. Overwrite?" % path) != QMessageBox.Yes:
                return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        # validate it loads
        from .. import pdk as pdkmod
        try:
            pdkmod._registry = None
            pdkmod.get(name)
        except Exception as e:
            QMessageBox.warning(self, tr("error"),
                                "written but failed to load:\n%s" % e)
        self.new_pdk_name = name
        self.accept()


def Q__center(widget):
    from PyQt5.QtWidgets import QWidget, QHBoxLayout
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.addWidget(widget)
    lay.setAlignment(Qt.AlignCenter)
    lay.setContentsMargins(0, 0, 0, 0)
    return w
