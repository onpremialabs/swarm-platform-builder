"""Capacidad `literature`: descubrimiento de candidatos en bases bibliográficas (SPEC-034).

Entrypoint del registro: `search_literature`. Los candidatos salen **sin verificar**.
"""
from app.platform.capabilities.literature.discovery import (  # noqa: F401
    clean_query, search_literature, validate_sources,
)
from app.platform.capabilities.literature.models import (  # noqa: F401
    DEFAULT_SOURCES, KNOWN_SOURCES, BaseReport, Candidate, LiteratureQueryError,
    LiteratureResult, UnknownSourceError,
)
from app.platform.capabilities.literature.transport import LiteratureConfig, SourceError  # noqa: F401
from app.platform.capabilities.literature.verification import (  # noqa: F401
    DiscardedCandidate, VerificationResult, VerifiedCandidate, verify_candidates,
)
