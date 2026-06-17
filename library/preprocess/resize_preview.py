"""Resize-preview helpers shared by preprocess GUI surfaces.

The resize step scales images to cover the selected constant-token bucket and
then center-crops to that bucket. This module exposes the same geometry without
touching files, so GUI previews can show what preprocessing will keep.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from library.datasets.buckets import DEFAULT_TARGET_RES, buckets_for_edges, choose_edge


@dataclass(frozen=True)
class CropRect:
    left: float
    top: float
    width: float
    height: float


@dataclass(frozen=True)
class ResizePreview:
    source_size: tuple[int, int]
    target_edge: int
    bucket_size: tuple[int, int]
    kept_rect: CropRect


def normalize_target_res(target_res: Iterable[int] | int | str | None) -> list[int]:
    """Normalize config-style ``target_res`` values into a non-empty int list."""
    if target_res is None:
        return list(DEFAULT_TARGET_RES)
    if isinstance(target_res, int):
        return [target_res]
    if isinstance(target_res, str):
        raw = target_res.strip()
        if not raw:
            return list(DEFAULT_TARGET_RES)
        return [int(part.strip()) for part in raw.split(",") if part.strip()]
    values = [int(value) for value in target_res]
    return values or list(DEFAULT_TARGET_RES)


def compute_resize_preview(
    width: int, height: int, target_res: Iterable[int] | int | str | None = None
) -> ResizePreview:
    """Return the bucket and source-space crop rect used by preprocessing."""
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")

    tiers = normalize_target_res(target_res)
    edge = choose_edge(width, height, tiers)
    bucket_w, bucket_h = _nearest_aspect_bucket(
        width, height, buckets_for_edges([edge])
    )

    source_ar = width / height
    bucket_ar = bucket_w / bucket_h
    if source_ar > bucket_ar:
        kept_h = float(height)
        kept_w = kept_h * bucket_ar
        left = (width - kept_w) / 2.0
        top = 0.0
    else:
        kept_w = float(width)
        kept_h = kept_w / bucket_ar
        left = 0.0
        top = (height - kept_h) / 2.0

    return ResizePreview(
        source_size=(width, height),
        target_edge=edge,
        bucket_size=(bucket_w, bucket_h),
        kept_rect=CropRect(left=left, top=top, width=kept_w, height=kept_h),
    )


def _nearest_aspect_bucket(
    width: int, height: int, buckets: Iterable[tuple[int, int]]
) -> tuple[int, int]:
    ar = width / height
    return min(buckets, key=lambda bucket: abs(bucket[0] / bucket[1] - ar))
