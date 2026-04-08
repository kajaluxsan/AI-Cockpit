"""Extract candidate photos from CV files (PDF / DOCX).

The idea is simple: most Swiss CVs embed a profile photo on the first page.
We pull all embedded images from the document, score them by size + aspect
ratio (portraits roughly between 0.6 and 1.4), pick the best candidate and
write it to the CV storage directory next to the CV file. The returned URL is
the relative path served by ``/api/candidates/{id}/photo``.

This module is intentionally tolerant: any failure (corrupt PDF, no images,
weird format) returns ``None`` so the candidate just falls back to the
initials avatar in the UI.
"""

from __future__ import annotations

import io
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

PHOTO_STORAGE_DIR = Path(os.getenv("CV_STORAGE_DIR", "/data/cv")) / "photos"

# Heuristic bounds for what counts as a portrait photo.
MIN_BYTES = 2_000          # discard tiny icons / logos
MAX_BYTES = 5_000_000      # discard giant background images
MIN_DIMENSION = 80         # too small to be a profile picture
MAX_DIMENSION = 4000       # too big — probably a page background scan
MIN_ASPECT = 0.55          # width / height — portraits aren't perfectly square
MAX_ASPECT = 1.45


@dataclass
class _Image:
    data: bytes
    width: int
    height: int
    ext: str

    @property
    def aspect(self) -> float:
        if self.height == 0:
            return 0.0
        return self.width / self.height

    @property
    def area(self) -> int:
        return self.width * self.height


def extract_photo(filename: str | None, data: bytes | None) -> str | None:
    """Try to find a profile photo inside the CV.

    Returns the absolute storage path of the saved JPEG/PNG, or None if no
    suitable image was found.
    """
    if not data or not filename:
        return None
    name = filename.lower()
    try:
        if name.endswith(".pdf"):
            images = _images_from_pdf(data)
        elif name.endswith(".docx"):
            images = _images_from_docx(data)
        else:
            return None
    except Exception as exc:
        logger.warning(f"Photo extraction failed for {filename}: {exc}")
        return None

    portrait = _pick_best_portrait(images)
    if not portrait:
        return None
    return _store_photo(portrait)


def _images_from_pdf(data: bytes) -> list[_Image]:
    """Use pypdf to walk all pages and collect embedded images."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    out: list[_Image] = []
    # Look at the first 3 pages — profile photos are essentially always on
    # page 1, and scanning more pages just adds noise (logos, icons).
    for page in reader.pages[:3]:
        try:
            page_images = page.images
        except Exception:
            continue
        for img in page_images:
            try:
                payload = img.data
            except Exception:
                continue
            if not payload or len(payload) < MIN_BYTES or len(payload) > MAX_BYTES:
                continue
            width, height, ext = _probe_image(payload)
            if not width or not height:
                continue
            out.append(_Image(payload, width, height, ext))
    return out


def _images_from_docx(data: bytes) -> list[_Image]:
    """Walk DOCX related parts to find embedded images."""
    import docx

    document = docx.Document(io.BytesIO(data))
    out: list[_Image] = []
    for rel in document.part.rels.values():
        target = getattr(rel, "target_part", None)
        if target is None:
            continue
        content_type = getattr(target, "content_type", "") or ""
        if not content_type.startswith("image/"):
            continue
        payload = getattr(target, "blob", None)
        if not payload or len(payload) < MIN_BYTES or len(payload) > MAX_BYTES:
            continue
        width, height, ext = _probe_image(payload)
        if not width or not height:
            continue
        out.append(_Image(payload, width, height, ext))
    return out


def _probe_image(data: bytes) -> tuple[int, int, str]:
    """Return (width, height, extension) for a binary image, or (0,0,'') on
    failure. Tries Pillow first, falls back to a tiny header sniffer so we
    don't introduce a hard dependency on Pillow."""
    try:
        from PIL import Image  # type: ignore

        with Image.open(io.BytesIO(data)) as im:
            fmt = (im.format or "").lower()
            ext = "jpg" if fmt in ("jpeg", "jpg") else (fmt or "png")
            return im.width, im.height, ext
    except Exception:
        pass
    return _sniff_dimensions(data)


def _sniff_dimensions(data: bytes) -> tuple[int, int, str]:
    """Tiny binary sniffer for JPEG / PNG headers. Good enough as a fallback
    when Pillow isn't installed."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            width = int.from_bytes(data[16:20], "big")
            height = int.from_bytes(data[20:24], "big")
            return width, height, "png"
        if data[:2] == b"\xff\xd8":
            # JPEG: walk markers until SOF0 (0xC0)
            i = 2
            while i < len(data):
                if data[i] != 0xFF:
                    break
                marker = data[i + 1]
                seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
                if marker in (0xC0, 0xC1, 0xC2):
                    height = int.from_bytes(data[i + 5 : i + 7], "big")
                    width = int.from_bytes(data[i + 7 : i + 9], "big")
                    return width, height, "jpg"
                i += 2 + seg_len
    except Exception:
        return 0, 0, ""
    return 0, 0, ""


def _pick_best_portrait(images: list[_Image]) -> _Image | None:
    """Score images by size + portrait-ness and return the best one."""
    candidates = [
        im
        for im in images
        if MIN_DIMENSION <= im.width <= MAX_DIMENSION
        and MIN_DIMENSION <= im.height <= MAX_DIMENSION
        and MIN_ASPECT <= im.aspect <= MAX_ASPECT
    ]
    if not candidates:
        return None
    # Prefer larger area but penalise non-portrait aspect
    def score(im: _Image) -> float:
        portrait_bonus = 1.0 - abs(im.aspect - 0.8)  # 0.8 = ideal portrait
        return im.area * (1.0 + portrait_bonus)

    return max(candidates, key=score)


def _store_photo(image: _Image) -> str | None:
    try:
        PHOTO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning(f"Cannot create photo storage dir: {exc}")
        return None
    slug = f"{uuid.uuid4().hex}.{image.ext}"
    path = PHOTO_STORAGE_DIR / slug
    try:
        path.write_bytes(image.data)
    except Exception as exc:
        logger.exception(f"Failed to store photo: {exc}")
        return None
    return str(path)
