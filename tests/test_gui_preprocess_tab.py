"""Regression tests for GUI preprocess-profile persistence."""

from __future__ import annotations

import os


def test_preprocess_tab_persists_default_target_res_to_variant():
    """The GUI profile should show the resolution tiers it will use.

    ``[1024]`` is the default tier, but it must still be written to the active
    gui-method variant when the Preprocess tab saves. Otherwise users see the
    resolution selection reset/vanish from the profile even though the widget
    accepted the value.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from gui import _load, variant_path
    from gui.tabs.preprocess_tab import PreprocessingTab

    app = QApplication.instance() or QApplication([])
    assert app is not None

    variant = "custom/__pytest_preprocess_target_res__"
    path = variant_path(variant)
    old_text = path.read_text(encoding="utf-8") if path.exists() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[variant]\nfamily = "lora"\n', encoding="utf-8")

    tab = None
    try:
        tab = PreprocessingTab()
        tab.set_variant(variant, method="lora")

        assert tab.persist_preprocess_inputs()

        meta = _load(path)["variant"]
        assert meta["target_res"] == [1024]
    finally:
        if tab is not None:
            tab.deleteLater()
        if old_text is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(old_text, encoding="utf-8")
