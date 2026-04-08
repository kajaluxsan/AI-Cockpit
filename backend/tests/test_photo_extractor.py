"""Tests for the CV photo picker heuristic.

The picker receives a list of ``_Image`` candidates from pypdf / python-docx
and must return the best portrait-like photo — or None if nothing qualifies.
This logic is the main thing that actually decides what shows up as the
avatar in the UI, so we want the edge cases pinned.
"""

from __future__ import annotations

from app.services.photo_extractor import _Image, _pick_best_portrait


def _img(width: int, height: int, data: bytes = b"x" * 3000) -> _Image:
    return _Image(data=data, width=width, height=height, ext="jpg")


def test_pick_best_portrait_picks_largest_portrait():
    # Several candidates — the 400x500 portrait beats the tiny and the square
    candidates = [
        _img(50, 50),           # too small, filtered out
        _img(300, 100),         # aspect ratio too landscape, filtered
        _img(200, 200),         # square, qualifies but smaller area
        _img(400, 500),         # proper portrait, biggest
        _img(100, 100),         # square, smaller
    ]
    best = _pick_best_portrait(candidates)
    assert best is not None
    assert (best.width, best.height) == (400, 500)


def test_pick_best_portrait_returns_none_when_only_landscapes():
    candidates = [
        _img(1000, 300),         # banner
        _img(1600, 400),         # page background
        _img(50, 50),            # icon
    ]
    assert _pick_best_portrait(candidates) is None


def test_pick_best_portrait_respects_max_dimensions():
    # A huge 5000x6000 image is probably a scanned page, not a portrait
    candidates = [
        _img(5000, 6000),
        _img(300, 400),           # small but a proper portrait
    ]
    best = _pick_best_portrait(candidates)
    assert best is not None
    assert (best.width, best.height) == (300, 400)


def test_pick_best_portrait_empty_list():
    assert _pick_best_portrait([]) is None
