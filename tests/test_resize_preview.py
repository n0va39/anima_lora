import pytest

from library.datasets.buckets import buckets_for_edges, choose_edge
from library.preprocess.resize_preview import (
    compute_resize_preview,
    normalize_target_res,
)


def test_resize_preview_uses_preprocess_bucket_tier():
    preview = compute_resize_preview(1440, 2560, [768, 1024])

    assert preview.target_edge == choose_edge(1440, 2560, [768, 1024])
    assert preview.bucket_size in buckets_for_edges([preview.target_edge])
    assert preview.kept_rect.width == pytest.approx(1440)
    assert preview.kept_rect.left == pytest.approx(0)
    assert preview.kept_rect.top > 0


def test_resize_preview_keeps_full_frame_when_aspect_matches_bucket():
    preview = compute_resize_preview(1008, 1024, 1024)

    assert preview.bucket_size == (1008, 1024)
    assert preview.kept_rect.left == pytest.approx(0)
    assert preview.kept_rect.top == pytest.approx(0)
    assert preview.kept_rect.width == pytest.approx(1008)
    assert preview.kept_rect.height == pytest.approx(1024)


def test_normalize_target_res_accepts_config_shapes():
    assert normalize_target_res("768, 1024") == [768, 1024]
    assert normalize_target_res(1024) == [1024]
    assert normalize_target_res([896, 1024]) == [896, 1024]
