"""Email template CRUD.

The recruiter edits templates from the Settings → Templates screen. Every
template is keyed by ``(name, language)`` so the same template can ship in
German, English, French and Italian simultaneously. One template per
language can be flagged ``is_signature=True`` to be used as the
``{{signature}}`` block in other templates.

Everything here is session-protected via the router dependency wired in
``app.main``; no per-endpoint auth check needed.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.email_template import EmailTemplate
from app.services.email_templates import render_preview

router = APIRouter()


class TemplateOut(BaseModel):
    id: int
    name: str
    language: str
    subject: str
    body: str
    is_signature: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_row(cls, row: EmailTemplate) -> "TemplateOut":
        return cls(
            id=row.id,
            name=row.name,
            language=row.language,
            subject=row.subject,
            body=row.body,
            is_signature=row.is_signature,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    language: str = Field(default="de", min_length=2, max_length=10)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    is_signature: bool = False


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    language: str | None = Field(default=None, min_length=2, max_length=10)
    subject: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, min_length=1)
    is_signature: bool | None = None


class TemplatePreview(BaseModel):
    subject: str
    body: str


@router.get("/", response_model=list[TemplateOut])
async def list_templates(
    language: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[TemplateOut]:
    """Return all templates, optionally filtered by language."""
    query = select(EmailTemplate).order_by(
        EmailTemplate.is_signature.desc(),
        EmailTemplate.name.asc(),
        EmailTemplate.language.asc(),
    )
    if language:
        query = query.where(EmailTemplate.language == language)
    rows = (await db.execute(query)).scalars().all()
    return [TemplateOut.from_orm_row(r) for r in rows]


@router.post("/", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate, db: AsyncSession = Depends(get_db)
) -> TemplateOut:
    row = EmailTemplate(
        name=payload.name.strip(),
        language=payload.language.strip().lower(),
        subject=payload.subject,
        body=payload.body,
        is_signature=payload.is_signature,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.info(
            f"Templates: duplicate (name={payload.name!r}, lang={payload.language!r}): {exc.orig}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A template with this name + language already exists.",
        )
    await db.refresh(row)
    logger.info(
        f"Templates: created id={row.id} name={row.name!r} lang={row.language!r} "
        f"signature={row.is_signature}"
    )
    return TemplateOut.from_orm_row(row)


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: int, db: AsyncSession = Depends(get_db)
) -> TemplateOut:
    row = await db.get(EmailTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return TemplateOut.from_orm_row(row)


@router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: int,
    payload: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    row = await db.get(EmailTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")

    data = payload.model_dump(exclude_unset=True)
    if "language" in data and data["language"]:
        data["language"] = data["language"].strip().lower()
    if "name" in data and data["name"]:
        data["name"] = data["name"].strip()
    for k, v in data.items():
        setattr(row, k, v)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.info(f"Templates: update {template_id} conflict: {exc.orig}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A template with this name + language already exists.",
        )
    await db.refresh(row)
    logger.info(f"Templates: updated id={row.id} fields={list(data.keys())}")
    return TemplateOut.from_orm_row(row)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    result = await db.execute(
        sa_delete(EmailTemplate).where(EmailTemplate.id == template_id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.commit()
    logger.info(f"Templates: deleted id={template_id}")


@router.post("/{template_id}/preview", response_model=TemplatePreview)
async def preview_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
) -> TemplatePreview:
    """Render the template against canned sample data for the UI preview."""
    row = await db.get(EmailTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    rendered = await render_preview(db, row)
    return TemplatePreview(subject=rendered.subject, body=rendered.body)
