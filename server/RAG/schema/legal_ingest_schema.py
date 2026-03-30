import os
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, validator

LegalNodeType = Literal["CHUONG", "MUC", "DIEU", "KHOAN", "DIEM", "DOAN"]


@dataclass
class LegalIngestSettings:
    supabase_url: str
    supabase_service_role_key: str
    openai_api_key: str
    embedding_model: str = "text-embedding-3-large"
    extraction_model: str = "gpt-4o-mini"
    max_upload_mb: int = 20
    embedding_dimensions: int = 1024

    @classmethod
    def from_env(cls) -> "LegalIngestSettings":
        return cls(
            supabase_url=os.getenv("SUPABASE_URL", "").strip(),
            supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large").strip(),
            extraction_model=os.getenv("LEGAL_EXTRACTION_MODEL", "gpt-4o-mini").strip(),
            max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "20")),
            embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "1024")),
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


class ParsedSegment(BaseModel):
    segment_ref: str
    parent_ref: Optional[str] = None
    segment_text: str
    detected_type: LegalNodeType
    ky_hieu_hint: Optional[str] = None
    thu_tu_hint: Optional[int] = None
    hierarchy_title: Optional[str] = None
    parent_context: Optional[str] = None


class ExtractedNode(BaseModel):
    noidung: str
    loai_muc: LegalNodeType
    ky_hieu: Optional[str] = None
    thu_tu: Optional[int] = None
    parent_ref: Optional[str] = None
    rela: List[str] = Field(default_factory=list)
    min_km: Optional[float] = None
    max_km: Optional[float] = None
    confidence: float = 0.0

    @validator("noidung")
    @classmethod
    def validate_noidung(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("noidung khong duoc rong")
        return normalized

    @validator("ky_hieu")
    @classmethod
    def validate_ky_hieu(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 50:
            raise ValueError("ky_hieu qua dai")
        return normalized

    @validator("rela")
    @classmethod
    def validate_rela(cls, value: List[str]) -> List[str]:
        normalized = []
        for item in value or []:
            if not isinstance(item, str):
                raise ValueError("rela phai la mang string")
            cleaned = item.strip()
            if cleaned:
                normalized.append(cleaned[:100])
        seen = set()
        deduped = []
        for item in normalized:
            lowered = item.lower()
            if lowered not in seen:
                seen.add(lowered)
                deduped.append(item)
        return deduped


class ParsedNodeResult(BaseModel):
    segment_ref: str
    parent_ref: Optional[str] = None
    source_segment: ParsedSegment
    extracted_json: Dict[str, Any]
    normalized_node: Optional[ExtractedNode] = None
    is_validated: bool = False
    validation_errors: List[str] = Field(default_factory=list)
    inserted_id: Optional[int] = None
    embedding_error: Optional[str] = None
    insert_error: Optional[str] = None


class IngestPreviewNode(BaseModel):
    segment_ref: str
    loai_muc: Optional[str] = None
    ky_hieu: Optional[str] = None
    thu_tu: Optional[int] = None
    noidung: str
    parent_ref: Optional[str] = None
    inserted_id: Optional[int] = None
    is_validated: bool = False
    validation_errors: List[str] = Field(default_factory=list)


class LegalIngestResponse(BaseModel):
    success: bool
    file_name: str
    segments_count: int
    parsed_count: int
    validated_count: int
    inserted_count: int
    failed_count: int
    preview: List[IngestPreviewNode]
