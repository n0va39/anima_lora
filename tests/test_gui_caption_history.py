from __future__ import annotations

from gui.tabs.image_tab import _append_history, _read_history


def test_caption_history_records_order_correction_reason(tmp_path):
    caption = tmp_path / "sample.txt"

    _append_history(caption, "1girl\nhatsune miku", reason="order_correction")
    _append_history(caption, "1girl\nhatsune miku", reason="save")

    history = _read_history(caption)

    assert len(history) == 1
    assert history[0]["text"] == "1girl\nhatsune miku"
    assert history[0]["reason"] == "order_correction"
