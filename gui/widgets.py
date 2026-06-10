"""Reusable Qt widgets + the config-form field factory.

Holds the lazy-tab mixin, the multi-scale ``target_res`` checkbox row, the
``_widget``/``_read`` pair that maps a config value to/from an editor widget,
and the aspect-preserving image label. Pulled out of the package root so the
widget code lives apart from the Qt-free config logic.
"""

from __future__ import annotations

import json
import re
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QWidget,
    QVBoxLayout,
)

from gui.i18n import t

# flash4 is not supported yet (flash-attention-sm120 disabled)
_ATTN_MODES = ["flex", "flash"]


class LazyTabMixin:
    """Defer a tab's first expensive scan until the tab is actually opened.

    Several tabs walk dataset/checkpoint directories (and the Merge tab reads
    safetensors keys) during construction. Doing that for *every* tab up front
    is what made the window slow to appear, even though only the first tab is
    visible at launch. Mixing this in lets construction stay cheap: the heavy
    work runs on the first ``showEvent`` — i.e. when the user selects the tab —
    and exactly once thereafter. Subclasses override ``_lazy_init``.

    Mix in BEFORE ``QWidget`` so ``super().showEvent`` resolves to Qt's.
    """

    _lazy_done = False

    def showEvent(self, event):  # noqa: N802 — Qt event handler name
        super().showEvent(event)
        if not self._lazy_done:
            self._lazy_done = True
            self._lazy_init()

    def _lazy_init(self) -> None:
        """Run the tab's first directory scan / classification. Override."""


# Allowed multi-scale tiers — mirrors library.datasets.buckets.ALLOWED_TARGET_RES
# (hardcoded so the GUI import stays light / library-free).
_TARGET_RES_TIERS = (512, 768, 896, 1024, 1280, 1536)

# High-cost tiers: large per-image token counts + an extra compiled block
# graph each. Flagged in the GUI so users don't casually enable them.
_TARGET_RES_DANGER = {1280: 6300, 1536: 8640}


class _TargetResWidget(QWidget):
    """Horizontal row of tier checkboxes for the multi-scale ``target_res`` knob.

    Reads/writes a list of edge ints (e.g. ``[1024, 1536]``). Never returns an
    empty list — unchecking everything falls back to ``[1024]`` (the legacy
    single ~1MP tier) so preprocess/train always have a valid tier.

    The 1280/1536 tiers are visually flagged as "dangerous" (high token count
    + extra compile graph / VRAM) via colour + an i18n tooltip.
    """

    changed = Signal()

    def __init__(self, selected) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        sel = {int(e) for e in selected} if selected else set()
        self._boxes: dict[int, QCheckBox] = {}
        for edge in _TARGET_RES_TIERS:
            cb = QCheckBox(str(edge))
            cb.setChecked(edge in sel)
            cb.toggled.connect(self.changed)
            if edge in _TARGET_RES_DANGER:
                cb.setStyleSheet("QCheckBox { color: #d9822b; font-weight: bold; }")
                cb.setToolTip(
                    t(
                        "target_res_danger_tooltip",
                        edge=edge,
                        tokens=_TARGET_RES_DANGER[edge],
                    )
                )
            lay.addWidget(cb)
            self._boxes[edge] = cb
        lay.addStretch(1)

    def value(self) -> list[int]:
        out = [e for e, cb in self._boxes.items() if cb.isChecked()]
        return out or [1024]


class _SamplePromptsWidget(QWidget):
    """Structured editor for train.py's one-line sample prompt syntax."""

    changed = Signal()

    _COL_PROMPT = 0
    _COL_W = 1
    _COL_H = 2
    _COL_STEPS = 3
    _COL_SEED = 4
    _COL_SCALE = 5
    _COL_GUIDANCE = 6
    _COL_NEGATIVE = 7
    _COL_EXTRA = 8

    def __init__(self, prompts) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                t("sample_prompt_col_prompt"),
                t("sample_prompt_col_width"),
                t("sample_prompt_col_height"),
                t("sample_prompt_col_steps"),
                t("sample_prompt_col_seed"),
                t("sample_prompt_col_cfg"),
                t("sample_prompt_col_guidance"),
                t("sample_prompt_col_negative"),
                t("sample_prompt_col_extra"),
            ]
        )
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(self._COL_PROMPT, QHeaderView.Stretch)
        hdr.setSectionResizeMode(self._COL_NEGATIVE, QHeaderView.Stretch)
        hdr.setSectionResizeMode(self._COL_EXTRA, QHeaderView.ResizeToContents)
        for col in (
            self._COL_W,
            self._COL_H,
            self._COL_STEPS,
            self._COL_SEED,
            self._COL_SCALE,
            self._COL_GUIDANCE,
        ):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setMaximumHeight(220)
        lay.addWidget(self.table)

        row_lay = QHBoxLayout()
        row_lay.setContentsMargins(0, 0, 0, 0)
        add_btn = QPushButton(t("sample_prompt_add"))
        add_btn.clicked.connect(lambda: self._add_row({}))
        row_lay.addWidget(add_btn)
        remove_btn = QPushButton(t("sample_prompt_remove"))
        remove_btn.clicked.connect(self._remove_selected)
        row_lay.addWidget(remove_btn)
        row_lay.addStretch(1)
        hint = QLabel(t("sample_prompt_hint"))
        hint.setStyleSheet("color:#888;")
        row_lay.addWidget(hint)
        lay.addLayout(row_lay)

        rows = self._parse_prompts(prompts)
        if rows:
            for row in rows:
                self._add_row(row)
        else:
            self._add_row({})

    @staticmethod
    def _parse_prompts(prompts) -> list[dict[str, Any]]:
        if isinstance(prompts, (list, tuple)):
            lines = [str(p).strip() for p in prompts]
        elif prompts is None:
            lines = []
        else:
            lines = [ln.strip() for ln in str(prompts).splitlines()]
        return [
            _SamplePromptsWidget._parse_line(ln)
            for ln in lines
            if ln and not ln.startswith("#")
        ]

    @staticmethod
    def _parse_line(line: str) -> dict[str, Any]:
        parts = line.split(" --")
        out: dict[str, Any] = {"prompt": parts[0].strip()}
        extra: list[str] = []
        for part in parts[1:]:
            try:
                if m := re.match(r"w (\d+)$", part, re.IGNORECASE):
                    out["width"] = int(m.group(1))
                elif m := re.match(r"h (\d+)$", part, re.IGNORECASE):
                    out["height"] = int(m.group(1))
                elif m := re.match(r"s (\d+)$", part, re.IGNORECASE):
                    out["steps"] = int(m.group(1))
                elif m := re.match(r"d (\d+)$", part, re.IGNORECASE):
                    out["seed"] = int(m.group(1))
                elif m := re.match(r"l ([\d.]+)$", part, re.IGNORECASE):
                    out["scale"] = float(m.group(1))
                elif m := re.match(r"g ([\d.]+)$", part, re.IGNORECASE):
                    out["guidance"] = float(m.group(1))
                elif m := re.match(r"n (.+)$", part, re.IGNORECASE):
                    out["negative"] = m.group(1).strip()
                else:
                    extra.append("--" + part.strip())
            except ValueError:
                extra.append("--" + part.strip())
        if extra:
            out["extra"] = " ".join(extra)
        return out

    def _line_edit(self, text: str = "") -> QLineEdit:
        w = QLineEdit(text)
        w.textChanged.connect(self.changed)
        return w

    def _int_spin(
        self, value: int = 0, *, maximum: int = 8192, unset: int = 0
    ) -> QSpinBox:
        w = QSpinBox()
        w.setRange(unset, maximum)
        w.setSpecialValueText("")
        w.setValue(int(value or unset))
        w.valueChanged.connect(self.changed)
        return _no_wheel(w)

    def _seed_spin(self, value: int | None = None) -> QSpinBox:
        w = QSpinBox()
        w.setRange(-1, 2_147_483_647)
        w.setSpecialValueText("")
        w.setValue(-1 if value is None else int(value))
        w.valueChanged.connect(self.changed)
        return _no_wheel(w)

    def _float_spin(self, value: float = 0.0) -> QDoubleSpinBox:
        w = QDoubleSpinBox()
        w.setRange(0.0, 100.0)
        w.setDecimals(2)
        w.setSingleStep(0.5)
        w.setSpecialValueText("")
        w.setValue(float(value or 0.0))
        w.valueChanged.connect(self.changed)
        return _no_wheel(w)

    def _add_row(self, data: dict[str, Any]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setCellWidget(
            row, self._COL_PROMPT, self._line_edit(data.get("prompt", ""))
        )
        self.table.setCellWidget(
            row, self._COL_W, self._int_spin(data.get("width", 0))
        )
        self.table.setCellWidget(
            row, self._COL_H, self._int_spin(data.get("height", 0))
        )
        self.table.setCellWidget(
            row, self._COL_STEPS, self._int_spin(data.get("steps", 0), maximum=1000)
        )
        self.table.setCellWidget(
            row, self._COL_SEED, self._seed_spin(data.get("seed"))
        )
        self.table.setCellWidget(
            row, self._COL_SCALE, self._float_spin(data.get("scale", 0.0))
        )
        self.table.setCellWidget(
            row, self._COL_GUIDANCE, self._float_spin(data.get("guidance", 0.0))
        )
        self.table.setCellWidget(
            row, self._COL_NEGATIVE, self._line_edit(data.get("negative", ""))
        )
        self.table.setCellWidget(
            row, self._COL_EXTRA, self._line_edit(data.get("extra", ""))
        )
        self.changed.emit()

    def _remove_selected(self) -> None:
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            rows = [self.table.rowCount() - 1]
        for row in rows:
            if row >= 0:
                self.table.removeRow(row)
        if self.table.rowCount() == 0:
            self._add_row({})
        self.changed.emit()

    def _cell(self, row: int, col: int) -> QWidget:
        return self.table.cellWidget(row, col)

    def value(self) -> list[str]:
        lines: list[str] = []
        for row in range(self.table.rowCount()):
            prompt = self._cell(row, self._COL_PROMPT).text().strip()
            if not prompt:
                continue
            parts = [prompt]
            for col, flag in (
                (self._COL_W, "w"),
                (self._COL_H, "h"),
                (self._COL_STEPS, "s"),
            ):
                val = self._cell(row, col).value()
                if val > 0:
                    parts.append(f"--{flag} {val}")
            seed = self._cell(row, self._COL_SEED).value()
            if seed >= 0:
                parts.append(f"--d {seed}")
            for col, flag in ((self._COL_SCALE, "l"), (self._COL_GUIDANCE, "g")):
                val = self._cell(row, col).value()
                if val > 0:
                    parts.append(f"--{flag} {val:g}")
            negative = self._cell(row, self._COL_NEGATIVE).text().strip()
            if negative:
                parts.append(f"--n {negative}")
            extra = self._cell(row, self._COL_EXTRA).text().strip()
            if extra:
                parts.append(extra if extra.startswith("--") else "--" + extra)
            lines.append(" ".join(parts))
        return lines


def _no_wheel(w: QWidget) -> QWidget:
    """Stop a hovered combo/spin from changing value (and stealing focus) on
    mouse-wheel scroll — otherwise scrolling the form silently edits whichever
    dropdown the cursor passes over. The widget still works via click + keys."""
    w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    w.wheelEvent = lambda e: e.ignore()
    return w


def _widget(v: Any, key: str = "") -> QWidget:
    if key == "target_res":
        sel = v if isinstance(v, (list, tuple)) else ([v] if v else [1024])
        return _TargetResWidget(sel)
    if key == "sample_prompts":
        return _SamplePromptsWidget(v)
    if key == "attn_mode":
        w = QComboBox()
        w.addItems(_ATTN_MODES)
        idx = w.findText(str(v))
        if idx >= 0:
            w.setCurrentIndex(idx)
        return _no_wheel(w)
    if key == "sample_decode_inline":
        # Tri-state: stored as the literal string "auto" / "true" / "false"
        # (all three are accepted by library.config.cli_args._optional_bool).
        # Must precede the bool branch below so a bool value gets the combo,
        # not a plain checkbox that can't express "auto".
        w = QComboBox()
        w.addItems(["auto", "true", "false"])
        if v is None:
            cur = "auto"
        elif isinstance(v, bool):
            cur = "true" if v else "false"
        else:
            cur = str(v).strip().lower()
            if cur in ("", "none"):
                cur = "auto"
        idx = w.findText(cur)
        if idx >= 0:
            w.setCurrentIndex(idx)
        return _no_wheel(w)
    if isinstance(v, bool):
        w = QCheckBox()
        w.setChecked(v)
        return w
    if isinstance(v, int):
        w = QSpinBox()
        # Per-key range overrides for fields that legitimately exceed the
        # default 10k cap (silently clips otherwise). Keep these explicit
        # rather than raising the global ceiling — most int fields are
        # small (epochs, ranks, expert counts) and a 10k cap keeps the
        # user from typoing a giant value into them.
        if key == "min_pixels":
            w.setRange(0, 100_000_000)  # 100MP — covers any real image
        else:
            w.setRange(0, 10000)
        w.setValue(v)
        return _no_wheel(w)
    if isinstance(v, float):
        return QLineEdit(f"{v:g}")
    if isinstance(v, list):
        return QLineEdit(json.dumps(v))
    return QLineEdit(str(v))


def _read(w: QWidget, orig: Any = None) -> Any:
    if isinstance(w, _TargetResWidget):
        return w.value()
    if isinstance(w, _SamplePromptsWidget):
        return w.value()
    if isinstance(w, QPlainTextEdit):
        # sample_prompts box → list of non-empty, non-comment lines.
        return [
            ln.strip()
            for ln in w.toPlainText().splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
    if isinstance(w, QComboBox):
        return w.currentText()
    if isinstance(w, QCheckBox):
        return w.isChecked()
    if isinstance(w, QSpinBox):
        return w.value()
    txt = w.text()
    if isinstance(orig, float):
        try:
            return float(txt)
        except ValueError:
            pass
    if isinstance(orig, list):
        try:
            return json.loads(txt)
        except (json.JSONDecodeError, ValueError):
            pass
    # Normalize Windows-style backslashes pasted into path/string fields.
    # Forward slashes are valid on every OS Python runs on, and avoid
    # downstream TOML escape errors (e.g. "C:\Users" → \U is not a valid
    # TOML escape).
    if "\\" in txt:
        txt = txt.replace("\\", "/")
    return txt


class ScaledImageLabel(QLabel):
    def __init__(self):
        super().__init__()
        self._src: QPixmap | None = None
        self.setAlignment(Qt.AlignCenter)

    def set_source(self, pm: QPixmap):
        self._src = pm
        self._rescale()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._rescale()

    def _rescale(self):
        if self._src and not self._src.isNull():
            self.setPixmap(
                self._src.scaled(
                    self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
