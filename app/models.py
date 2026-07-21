from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FileResultMeta(object):
    size_bytes: int
    extension: str
    content_type: Optional[str] = None
    text_source: Optional[str] = None
    page_count: Optional[int] = None
    gpt_attempts: Optional[int] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None

    def to_dict(self):
        # type: () -> Dict[str, Any]
        return asdict(self)


@dataclass
class FileParseResult(object):
    filename: str
    success: bool
    meta: FileResultMeta
    fields: Optional[Dict[str, Any]] = None

    def to_dict(self):
        # type: () -> Dict[str, Any]
        return {
            "filename": self.filename,
            "success": self.success,
            "fields": self.fields,
            "meta": self.meta.to_dict(),
        }


@dataclass
class ParseResponse(object):
    request_id: str
    username: str
    results: List[FileParseResult] = field(default_factory=list)

    def to_dict(self):
        # type: () -> Dict[str, Any]
        return {
            "request_id": self.request_id,
            "username": self.username,
            "results": [item.to_dict() for item in self.results],
        }
