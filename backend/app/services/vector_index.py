"""Qdrant + BGE-M3 semantic index for candidates and jobs.

This module is feature-flagged: when ``qdrant_enabled`` is false (or when
any dependency is missing), every public helper becomes a no-op so the
rest of the app runs unchanged. That lets operators turn semantic
matching on/off without redeploying.

Design goals:

* **Lazy imports.** ``qdrant-client`` and ``fastembed`` are only imported
  on first use. This keeps cold-start fast and lets the backend boot
  even when the wheels aren't installed (e.g. during CI unit tests).
* **Defensive failure.** Any Qdrant / embedding failure logs a warning
  and degrades to "no semantic filter"; the caller then falls back to
  the deterministic scorer over the full set.
* **Hybrid ranking.** Vector search produces a top-K shortlist. The
  deterministic + LLM scorer is then applied to that shortlist only.
  That's "fusion" in the practical sense — final ranking blends
  semantic retrieval with explainable feature scoring.
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from app.config import get_settings
from app.models.candidate import Candidate
from app.models.job import Job

# Lazily-initialised globals. Holding instances at module level is fine
# here because both Qdrant client and fastembed models are thread-safe
# and amortising init over many calls matters for throughput.
_qdrant_client: Any = None
_embedder: Any = None
_init_lock = asyncio.Lock()
_collections_ready: bool = False
_vector_dim: int | None = None


# ---------------------------------------------------------------------------
# Text builders
# ---------------------------------------------------------------------------


def build_candidate_document(candidate: Candidate) -> str:
    """Flatten the candidate record into a single text blob.

    Keep the order consistent so incremental re-indexes don't churn
    embeddings unnecessarily. We include name, headline, summary, skills
    and a compact work history — the same fields the recruiter uses
    when skimming a profile.
    """
    parts: list[str] = []
    if candidate.full_name:
        parts.append(candidate.full_name)
    if candidate.headline:
        parts.append(candidate.headline)
    if candidate.location:
        parts.append(candidate.location)
    if candidate.summary:
        parts.append(candidate.summary)
    if candidate.skills:
        parts.append("Skills: " + ", ".join(str(s) for s in candidate.skills))
    if candidate.languages_spoken:
        parts.append(
            "Languages: " + ", ".join(str(l) for l in candidate.languages_spoken)
        )
    if candidate.work_history:
        titles = []
        for entry in candidate.work_history[:5]:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title") or entry.get("position") or ""
            company = entry.get("company") or entry.get("employer") or ""
            if title or company:
                titles.append(f"{title} @ {company}".strip(" @"))
        if titles:
            parts.append("Experience: " + "; ".join(titles))
    return "\n".join(p for p in parts if p)


def build_job_document(job: Job) -> str:
    """Flatten the job posting into a single text blob."""
    parts: list[str] = []
    if job.title:
        parts.append(job.title)
    if job.company:
        parts.append(job.company)
    if job.location:
        parts.append(job.location)
    if job.description:
        parts.append(job.description)
    if job.required_skills:
        parts.append("Required: " + ", ".join(str(s) for s in job.required_skills))
    if job.nice_to_have_skills:
        parts.append(
            "Nice to have: " + ", ".join(str(s) for s in job.nice_to_have_skills)
        )
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Lazy init
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
    return bool(get_settings().qdrant_enabled)


async def _ensure_ready() -> bool:
    """Initialise Qdrant client + embedder + collections on first use.

    Returns ``True`` when the index is ready to take reads/writes and
    ``False`` when any dependency failed (caller should degrade).
    """
    global _qdrant_client, _embedder, _collections_ready, _vector_dim

    if not is_enabled():
        return False
    if _collections_ready and _qdrant_client is not None and _embedder is not None:
        return True

    async with _init_lock:
        if _collections_ready and _qdrant_client is not None and _embedder is not None:
            return True

        settings = get_settings()
        try:
            # Lazy import: keep fastembed / qdrant-client out of the
            # import path when the feature is off.
            from fastembed import TextEmbedding  # type: ignore
            from qdrant_client import AsyncQdrantClient  # type: ignore
            from qdrant_client.http import models as qm  # type: ignore
        except ImportError as exc:
            logger.warning(
                f"Semantic matching disabled: missing dependency ({exc}). "
                "Install qdrant-client and fastembed to enable."
            )
            return False

        try:
            _embedder = TextEmbedding(model_name=settings.embedding_model)
        except Exception as exc:
            logger.warning(
                f"Failed to load embedding model {settings.embedding_model}: {exc}"
            )
            _embedder = None
            return False

        # Determine vector dimension by embedding a single probe string.
        # fastembed returns a generator of numpy arrays.
        try:
            probe = next(iter(_embedder.embed(["probe"])))
            _vector_dim = int(len(probe))
        except Exception as exc:
            logger.warning(f"Failed to probe embedding dimension: {exc}")
            return False

        try:
            _qdrant_client = AsyncQdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                prefer_grpc=False,
            )
        except Exception as exc:
            logger.warning(f"Failed to create Qdrant client: {exc}")
            return False

        # Ensure both collections exist with the right dimension.
        try:
            existing = {
                c.name
                for c in (await _qdrant_client.get_collections()).collections
            }
            for coll in (
                settings.qdrant_collection_candidates,
                settings.qdrant_collection_jobs,
            ):
                if coll not in existing:
                    await _qdrant_client.create_collection(
                        collection_name=coll,
                        vectors_config=qm.VectorParams(
                            size=_vector_dim,
                            distance=qm.Distance.COSINE,
                        ),
                    )
                    logger.info(
                        f"Qdrant: created collection {coll} (dim={_vector_dim})"
                    )
        except Exception as exc:
            logger.warning(f"Qdrant collection setup failed: {exc}")
            return False

        _collections_ready = True
        logger.info(
            f"Semantic matching ready (model={settings.embedding_model}, "
            f"dim={_vector_dim}, qdrant={settings.qdrant_url})"
        )
        return True


async def _embed(text: str) -> list[float] | None:
    """Embed a single document. Returns None on failure."""
    if not text.strip():
        return None
    if _embedder is None:
        return None
    try:
        # fastembed returns numpy arrays; convert to plain list for Qdrant.
        # Run in a thread because the ONNX inference is CPU-bound and blocks.
        def _run() -> list[float]:
            return [float(x) for x in next(iter(_embedder.embed([text])))]

        return await asyncio.to_thread(_run)
    except Exception as exc:
        logger.warning(f"Embedding failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Upsert / delete
# ---------------------------------------------------------------------------


async def index_candidate(candidate: Candidate) -> bool:
    """Upsert one candidate into the vector index. No-op when disabled."""
    if not await _ensure_ready():
        return False
    # Anonymised candidates must not be vectorised — right to be
    # forgotten is a hard constraint.
    if getattr(candidate, "anonymised", False):
        await delete_candidate(candidate.id)
        return True
    doc = build_candidate_document(candidate)
    vec = await _embed(doc)
    if vec is None:
        return False
    settings = get_settings()
    try:
        from qdrant_client.http import models as qm  # type: ignore

        await _qdrant_client.upsert(
            collection_name=settings.qdrant_collection_candidates,
            points=[
                qm.PointStruct(
                    id=candidate.id,
                    vector=vec,
                    payload={
                        "candidate_id": candidate.id,
                        "status": (
                            candidate.status.value
                            if hasattr(candidate.status, "value")
                            else str(candidate.status)
                        ),
                        "location": candidate.location,
                    },
                )
            ],
        )
        return True
    except Exception as exc:
        logger.warning(f"Qdrant upsert (candidate {candidate.id}) failed: {exc}")
        return False


async def index_job(job: Job) -> bool:
    """Upsert one job into the vector index. No-op when disabled."""
    if not await _ensure_ready():
        return False
    doc = build_job_document(job)
    vec = await _embed(doc)
    if vec is None:
        return False
    settings = get_settings()
    try:
        from qdrant_client.http import models as qm  # type: ignore

        await _qdrant_client.upsert(
            collection_name=settings.qdrant_collection_jobs,
            points=[
                qm.PointStruct(
                    id=job.id,
                    vector=vec,
                    payload={
                        "job_id": job.id,
                        "status": (
                            job.status.value
                            if hasattr(job.status, "value")
                            else str(job.status)
                        ),
                        "location": job.location,
                    },
                )
            ],
        )
        return True
    except Exception as exc:
        logger.warning(f"Qdrant upsert (job {job.id}) failed: {exc}")
        return False


async def delete_candidate(candidate_id: int) -> bool:
    if not await _ensure_ready():
        return False
    settings = get_settings()
    try:
        from qdrant_client.http import models as qm  # type: ignore

        await _qdrant_client.delete(
            collection_name=settings.qdrant_collection_candidates,
            points_selector=qm.PointIdsList(points=[candidate_id]),
        )
        return True
    except Exception as exc:
        logger.warning(f"Qdrant delete (candidate {candidate_id}) failed: {exc}")
        return False


async def delete_job(job_id: int) -> bool:
    if not await _ensure_ready():
        return False
    settings = get_settings()
    try:
        from qdrant_client.http import models as qm  # type: ignore

        await _qdrant_client.delete(
            collection_name=settings.qdrant_collection_jobs,
            points_selector=qm.PointIdsList(points=[job_id]),
        )
        return True
    except Exception as exc:
        logger.warning(f"Qdrant delete (job {job_id}) failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def search_jobs_for_candidate(
    candidate: Candidate, top_k: int | None = None
) -> list[tuple[int, float]]:
    """Return ``[(job_id, score)]`` for the top semantic neighbours."""
    if not await _ensure_ready():
        return []
    settings = get_settings()
    vec = await _embed(build_candidate_document(candidate))
    if vec is None:
        return []
    try:
        hits = await _qdrant_client.search(
            collection_name=settings.qdrant_collection_jobs,
            query_vector=vec,
            limit=top_k or settings.semantic_top_k,
        )
        return [(int(h.id), float(h.score)) for h in hits]
    except Exception as exc:
        logger.warning(f"Qdrant search (jobs for cand {candidate.id}) failed: {exc}")
        return []


async def search_candidates_for_job(
    job: Job, top_k: int | None = None
) -> list[tuple[int, float]]:
    """Return ``[(candidate_id, score)]`` for the top semantic neighbours."""
    if not await _ensure_ready():
        return []
    settings = get_settings()
    vec = await _embed(build_job_document(job))
    if vec is None:
        return []
    try:
        hits = await _qdrant_client.search(
            collection_name=settings.qdrant_collection_candidates,
            query_vector=vec,
            limit=top_k or settings.semantic_top_k,
        )
        return [(int(h.id), float(h.score)) for h in hits]
    except Exception as exc:
        logger.warning(f"Qdrant search (candidates for job {job.id}) failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# Bulk reindex
# ---------------------------------------------------------------------------


async def reindex_all(
    candidates: list[Candidate], jobs: list[Job]
) -> dict[str, int]:
    """Re-embed + upsert every candidate and job.

    Returns a ``{"candidates": n, "jobs": m}`` counter for the caller to
    display. When semantic matching is disabled, both counters are 0.
    """
    counts = {"candidates": 0, "jobs": 0}
    if not await _ensure_ready():
        return counts
    for c in candidates:
        if getattr(c, "anonymised", False):
            continue
        if await index_candidate(c):
            counts["candidates"] += 1
    for j in jobs:
        if await index_job(j):
            counts["jobs"] += 1
    logger.info(f"Semantic reindex complete: {counts}")
    return counts
