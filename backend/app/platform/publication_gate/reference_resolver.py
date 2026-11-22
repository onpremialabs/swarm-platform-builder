"""Existencia y coincidencia de las referencias (SPEC-032 AC3 y AC4, FW V09 nivel 2).

Cada referencia se resuelve contra Crossref y, si no aparece, contra OpenAlex, por
DOI o —sin él— por título y autores. Los DOI de arXiv (`10.48550/…`) los registra
DataCite, no Crossref, así que se consultan primero allí (ADR-0011, enmienda). Determinista y **sin LLM**: el framework
documenta que un modelo que valida citas es justo el fallo que esto evita.

Tres decisiones (ADR-0011):

* **Falla cerrada.** Lo que no se puede comprobar es `not_verified` y bloquea:
  servicio caído, tiempo agotado, 429, respuesta inválida, varios candidatos
  igualmente plausibles o ninguno. Nunca se aprueba por ausencia de respuesta.
* **Solo metadatos de referencias salen de aquí**, nunca el texto del manuscrito, y por
  la puerta única de `platform/egress.py`.
* **La caché guarda solo positivos.** Cachear un fallo convertiría una caída
  transitoria en un bloqueo de 30 días.
"""
from __future__ import annotations

import asyncio
import difflib
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Optional
from urllib.parse import quote

from app.platform.metrics import observe_gate_external_error, observe_gate_reference
from app.platform.publication_gate.references import is_citable
from app.platform.publication_gate.types import CriterionResult, CriterionStatus

logger = logging.getLogger(__name__)

CRITERION = "reference_existence"

CROSSREF = "https://api.crossref.org/works"
OPENALEX = "https://api.openalex.org/works"
DATACITE = "https://api.datacite.org/dois"
#: Prefijo de los DOI de arXiv: los registra DataCite y Crossref responde 404.
DATACITE_PREFIXES = ("10.48550/",)


@dataclass(frozen=True)
class ResolverConfig:
    """Valores iniciales de AC3/AC4; el proyecto los fija en `gate.references`."""

    title_similarity: float = 0.90
    #: Fracción de los demás autores del registro que debe aparecer en la referencia.
    other_authors_ratio: float = 0.5
    timeout_s: float = 10.0
    retries: int = 2
    backoff_s: float = 1.0
    max_total_s: float = 120.0
    cache_ttl_days: float = 30.0
    candidates: int = 5
    contact_email: str = ""


@dataclass
class Canonical:
    """Registro bibliográfico normalizado, venga de Crossref o de OpenAlex."""

    provider: str
    doi: str
    title: str
    authors: list[str]  # apellidos, en orden
    year: Optional[int]
    journal: str
    preprint: bool = False


class Unavailable(Exception):
    """El servicio no dio una respuesta utilizable (red, 5xx, 429, JSON inválido)."""


# ── Normalización ───────────────────────────────────────────────────────────


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _ascii(text))


def normalize_doi(doi: str) -> str:
    d = (doi or "").strip().lower()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d)
    return d.strip()


def title_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, " ".join(_words(a)), " ".join(_words(b))).ratio()


def _family(name: str) -> str:
    words = _words(name)
    return words[-1] if words else ""


def authors_match(source_authors: str, record: list[str], ratio: float) -> Optional[str]:
    """`None` si coinciden; si no, el motivo."""
    if not record:
        return "el registro no trae autores"
    palabras = _words(source_authors)
    familias = [(_words(a) or [""])[-1] for a in record]

    def posicion(f: str) -> Optional[int]:
        return palabras.index(f) if f and f in palabras else None

    pos = [posicion(f) for f in familias]
    # El primer autor del registro debe ser también el primero que aparece.
    if pos[0] is None or any(p is not None and p < pos[0] for p in pos[1:]):
        return f"el primer autor del registro es «{record[0]}»"
    # Con «et al.» la lista de la referencia es parcial: solo se exige el primero.
    if re.search(r"\bet\.? al\b|\bet alii\b", _ascii(source_authors)):
        return None
    otros = [f for f in familias[1:] if f]
    if otros:
        presentes = sum(1 for f in otros if f in palabras)
        if presentes < ratio * len(otros):
            return f"solo coinciden {presentes} de {len(otros)} autores restantes"
    return None


def _abrevia(abbr: str, full: str) -> bool:
    """`abbr` es `full` abreviada: misma inicial y sus letras en orden («natl» ~ «national»)."""
    if not abbr or abbr[0] != full[:1]:
        return False
    it = iter(full)
    return all(ch in it for ch in abbr)


#: Palabras que no distinguen una publicación de otra: aparecen o no según cómo la cite
#: cada persona o cada base («Proc.», «2016 IEEE Conference…»). Medido con Crossref real.
_GENERICAS = {
    "the", "of", "de", "la", "el", "and", "y", "journal", "j", "proc", "proceedings",
    "conf", "conference", "annual", "int", "intl", "international", "symp", "symposium",
    "workshop", "on", "in",
}


def journals_match(a: str, b: str) -> bool:
    """¿Es la misma publicación? Tolera abreviaturas, el orden y las palabras genéricas.

    Cada palabra significativa de la cita más corta debe corresponder (igual o
    abreviada) a alguna de la otra, y se exige al menos el 60 %: es una señal débil —el
    título, los autores y el DOI pesan más— pero distingue «Nature» de «Science»
    y «Proc. Natl. Acad. Sci.» de «Proceedings of the National Academy of Sciences».
    """
    def significativas(texto: str) -> list[str]:
        return [w for w in _words(texto) if w not in _GENERICAS and not w.isdigit()]

    ta, tb = significativas(a), significativas(b)
    if not ta or not tb:
        return False
    corto, largo = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    coinciden = sum(1 for c in corto if any(c == w or _abrevia(c, w) for w in largo))
    return coinciden / len(corto) >= 0.6


def _year_ok(src: str, rec: Optional[int], preprint: bool) -> bool:
    try:
        y = int(str(src).strip()[:4])
    except ValueError:
        return False
    if rec is None:
        return False
    return y == rec or (preprint and abs(y - rec) <= 1)


# ── Proveedores ─────────────────────────────────────────────────────────────


def _from_crossref(item: dict) -> Canonical:
    parts = ((item.get("issued") or {}).get("date-parts") or [[None]])[0]
    return Canonical(
        provider="crossref",
        doi=normalize_doi(item.get("DOI", "")),
        title=(item.get("title") or [""])[0],
        authors=[a.get("family") or a.get("name", "") for a in item.get("author", [])],
        year=parts[0] if parts and parts[0] else None,
        journal=(item.get("container-title") or [""])[0],
        preprint=item.get("type") == "posted-content",
    )


def _from_openalex(item: dict) -> Canonical:
    source = ((item.get("primary_location") or {}).get("source") or {})
    return Canonical(
        provider="openalex",
        doi=normalize_doi(item.get("doi") or ""),
        title=item.get("title") or item.get("display_name") or "",
        authors=[
            ((a.get("author") or {}).get("display_name") or "")
            for a in item.get("authorships", [])
        ],
        year=item.get("publication_year"),
        journal=source.get("display_name") or "",
        preprint=item.get("type") == "preprint",
    )


def _from_datacite(item: dict) -> Canonical:
    attrs = (item.get("data") or {}).get("attributes") or {}
    types = attrs.get("types") or {}
    return Canonical(
        provider="datacite",
        doi=normalize_doi(attrs.get("doi") or ""),
        title=((attrs.get("titles") or [{}])[0] or {}).get("title", ""),
        authors=[
            c.get("familyName") or c.get("name", "") for c in attrs.get("creators") or []
        ],
        year=attrs.get("publicationYear"),
        journal=((attrs.get("container") or {}).get("title")) or attrs.get("publisher") or "",
        preprint=types.get("resourceTypeGeneral") == "Preprint"
        or str(attrs.get("doi") or "").lower().startswith(DATACITE_PREFIXES),
    )


Fetch = Callable[..., Awaitable[Any]]


async def _default_fetch(url: str, *, params=None, headers=None, timeout: float = 10.0):
    from app.platform.egress import safe_get

    return await safe_get(
        url, quien="publication_gate", params=params, headers=headers, timeout=timeout
    )


def fetch_for(quien: str) -> Fetch:
    """Un `fetch` que sale por la puerta de egress con la identidad `quien`.

    La compuerta usa `_default_fetch` (`publication_gate`); otra capacidad que reutilice
    el resolver (descubrimiento de literatura, SPEC-034/T22.2) pide el suyo para que la
    allowlist y el registro de egress la distingan.
    """
    async def fetch(url: str, *, params=None, headers=None, timeout: float = 10.0):
        from app.platform.egress import safe_get

        return await safe_get(url, quien=quien, params=params, headers=headers, timeout=timeout)

    return fetch


@dataclass(frozen=True)
class ResolverMetrics:
    """A dónde van las métricas del resolver. Por defecto, las de la compuerta."""

    reference: Callable[[str], None]
    external_error: Callable[[str, str], None]


#: Se resuelven al llamar (no al importar) para que un test o un despliegue que
#: sustituya `observe_gate_*` en este módulo lo vea.
GATE_METRICS = ResolverMetrics(
    reference=lambda outcome: observe_gate_reference(outcome),
    external_error=lambda provider, reason: observe_gate_external_error(provider, reason),
)
NO_METRICS = ResolverMetrics(reference=lambda outcome: None, external_error=lambda p, r: None)


# ── Caché de positivos ──────────────────────────────────────────────────────


class PositiveCache:
    """En memoria, por proceso. Solo guarda registros resueltos, con TTL."""

    def __init__(self, ttl_days: float = 30.0, clock: Callable[[], float] = time.time):
        self._ttl = ttl_days * 86400
        self._clock = clock
        self._data: dict[str, tuple[float, Canonical]] = {}

    def get(self, doi: str) -> Optional[Canonical]:
        hit = self._data.get(doi)
        if hit is None:
            return None
        if self._clock() - hit[0] > self._ttl:
            del self._data[doi]
            return None
        return hit[1]

    def put(self, doi: str, rec: Canonical) -> None:
        self._data[doi] = (self._clock(), rec)


# ── Resolución ──────────────────────────────────────────────────────────────


def _proveedor(url: str) -> str:
    if url.startswith(CROSSREF):
        return "crossref"
    return "datacite" if url.startswith(DATACITE) else "openalex"


class _Session:
    def __init__(self, cfg: ResolverConfig, fetch: Fetch, sleep, clock, cache: PositiveCache,
                 metrics: ResolverMetrics = GATE_METRICS,
                 user_agent: str = "AlejandrIA-PublicationGate/1.0"):
        self.cfg, self.fetch, self.sleep, self.clock, self.cache = cfg, fetch, sleep, clock, cache
        self.metrics = metrics
        self.started = clock()
        ua = user_agent
        # El correo de contacto identifica al cliente ante Crossref/OpenAlex (su «polite
        # pool»). Sale de la configuración, nunca del repositorio.
        from app.core.config import settings

        correo = cfg.contact_email or getattr(settings, "PUBLICATION_GATE_CONTACT_EMAIL", "")
        self.headers = {"User-Agent": f"{ua} (mailto:{correo})" if correo else ua}

    def expired(self) -> bool:
        return self.clock() - self.started > self.cfg.max_total_s

    async def get_json(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        """JSON de la respuesta, o `None` si es un 404 (no existe). Levanta `Unavailable`."""
        ultimo = "sin respuesta"
        for intento in range(self.cfg.retries + 1):
            if self.expired():
                raise Unavailable("tiempo máximo de evaluación agotado")
            try:
                r = await self.fetch(
                    url, params=params, headers=self.headers, timeout=self.cfg.timeout_s
                )
                if r.status_code == 404:
                    return None
                if r.status_code == 200:
                    try:
                        data = r.json()
                    except ValueError:
                        raise Unavailable("respuesta que no es JSON")
                    if not isinstance(data, dict):
                        raise Unavailable("respuesta con forma inesperada")
                    return data
                # 429 y 5xx: transitorios; se reintenta con espera, sin insistir más.
                ultimo = f"HTTP {r.status_code}"
                self.metrics.external_error(_proveedor(url), "rate_limited" if r.status_code == 429 else "http_error")
            except Unavailable as exc:
                ultimo = str(exc)
            except Exception as exc:  # red, TLS, tiempo agotado, egress bloqueado
                ultimo = f"{type(exc).__name__}: {exc}"
                self.metrics.external_error(_proveedor(url), "network")
            if intento < self.cfg.retries:
                await self.sleep(self.cfg.backoff_s * (2**intento))
        raise Unavailable(ultimo)


async def _lookup_doi(sess: _Session, doi: str) -> Optional[Canonical]:
    cached = sess.cache.get(doi)
    if cached:
        sess.metrics.reference("cache_hit")
        return cached
    errors = []
    fetchers = (_crossref_doi, _openalex_doi)
    if doi.startswith(DATACITE_PREFIXES):
        # El registrador de ese prefijo es la fuente de verdad: si responde, lo que
        # diga (incluido «no existe») es concluyente y no se pregunta a quien solo lo
        # indexa. Si no responde, se cae a los otros dos, que solo pueden aprobar si
        # el registro coincide en todo.
        try:
            rec = await _datacite_doi(sess, doi)
        except Unavailable as exc:
            errors.append(str(exc))
        else:
            if rec:
                sess.cache.put(doi, rec)
            return rec
    for fetcher in fetchers:
        try:
            rec = await fetcher(sess, doi)
        except Unavailable as exc:
            errors.append(str(exc))
            continue
        if rec:
            sess.cache.put(doi, rec)
            return rec
    if errors:
        # Un proveedor no respondió y el otro no lo conoce: no se puede afirmar
        # que el DOI no existe.
        raise Unavailable("; ".join(errors))
    return None


async def _crossref_doi(sess: _Session, doi: str) -> Optional[Canonical]:
    data = await sess.get_json(f"{CROSSREF}/{quote(doi, safe='/')}")
    return _from_crossref(data["message"]) if data and "message" in data else None


async def _datacite_doi(sess: _Session, doi: str) -> Optional[Canonical]:
    data = await sess.get_json(f"{DATACITE}/{quote(doi, safe='/')}")
    return _from_datacite(data) if data and "data" in data else None


async def _openalex_doi(sess: _Session, doi: str) -> Optional[Canonical]:
    data = await sess.get_json(f"{OPENALEX}/https://doi.org/{quote(doi, safe='/')}")
    return _from_openalex(data) if data else None


async def _search(sess: _Session, title: str, authors: str) -> list[Canonical]:
    """Candidatos por título y autores en Crossref y, si no hay, en OpenAlex."""
    errors = []
    n = sess.cfg.candidates
    plans = (
        (CROSSREF, {"query.bibliographic": f"{title} {authors}".strip(), "rows": n},
         lambda d: [_from_crossref(i) for i in (d.get("message") or {}).get("items", [])]),
        (OPENALEX, {"search": title, "per-page": n},
         lambda d: [_from_openalex(i) for i in d.get("results", [])]),
    )
    for url, params, parse in plans:
        try:
            data = await sess.get_json(url, params)
        except Unavailable as exc:
            errors.append(str(exc))
            continue
        found = [c for c in parse(data or {}) if c.doi]
        plausibles = [c for c in found if title_similarity(title, c.title) >= sess.cfg.title_similarity]
        if plausibles:
            return plausibles
    if errors:
        # Un proveedor sin respuesta deja sin comprobar lo que el otro no halló.
        raise Unavailable("; ".join(errors))
    return []


def _compare(src: dict, rec: Canonical, cfg: ResolverConfig) -> list[str]:
    """Discrepancias entre la referencia y el registro; vacío si coinciden."""
    issues = []
    sim = title_similarity(str(src.get("title", "")), rec.title)
    if sim < cfg.title_similarity:
        issues.append(f"título: similitud {sim:.2f} < {cfg.title_similarity:.2f}")
    if (m := authors_match(str(src.get("authors", "")), rec.authors, cfg.other_authors_ratio)):
        issues.append(f"autores: {m}")
    if str(src.get("year", "")).strip() and not _year_ok(src.get("year"), rec.year, rec.preprint):
        issues.append(f"año: {src.get('year')} frente a {rec.year}")
    if str(src.get("journal", "")).strip() and rec.journal and not journals_match(
        str(src["journal"]), rec.journal
    ):
        issues.append(f"revista: «{src['journal']}» frente a «{rec.journal}»")
    return issues


@dataclass
class ReferenceOutcome:
    status: CriterionStatus
    reason: str
    doi: str = ""
    provider: str = ""
    source: dict = field(default_factory=dict)
    #: Causa estructurada para quien reutiliza el resolver (SPEC-034/T22.2); la compuerta
    #: sigue usando `status` y `reason`. `not_found` | `mismatch` | `unavailable` |
    #: `no_search_data` | `no_match` | `ambiguous`; vacío si pasó.
    kind: str = ""


async def _resolve_one(sess: _Session, src: dict) -> ReferenceOutcome:
    cfg = sess.cfg
    doi = normalize_doi(str(src.get("doi", "")))
    try:
        if doi:
            rec = await _lookup_doi(sess, doi)
            if rec is None:
                return ReferenceOutcome(
                    CriterionStatus.FAILED, f"el DOI {doi} no existe en Crossref ni en OpenAlex",
                    kind="not_found",
                )
        else:
            title, authors = str(src.get("title", "")).strip(), str(src.get("authors", "")).strip()
            if not title or not authors:
                return ReferenceOutcome(
                    CriterionStatus.NOT_VERIFIED, "sin DOI ni título y autores con los que buscar",
                    kind="no_search_data",
                )
            cands = await _search(sess, title, authors)
            cands = [c for c in cands if not _compare({**src, "year": "", "journal": ""}, c, cfg)]
            dois = {c.doi for c in cands}
            if not dois:
                return ReferenceOutcome(
                    CriterionStatus.NOT_VERIFIED, "ninguna coincidencia fiable por título y autores",
                    kind="no_match",
                )
            if len(dois) > 1:
                # Varios registros pasan por título y autores (una misma obra con dos DOI,
                # o una homónima): el año y la revista de la cita desempatan. Si siguen
                # quedando varios, no se elige uno al azar.
                afinados = [c for c in cands if not _compare(src, c, cfg)]
                dois = {c.doi for c in afinados}
                if len(dois) == 1:
                    cands = afinados
            if not dois:
                return ReferenceOutcome(
                    CriterionStatus.NOT_VERIFIED,
                    "varios candidatos por título y autores y ninguno coincide en año y revista",
                    kind="no_match",
                )
            if len(dois) > 1:
                return ReferenceOutcome(
                    CriterionStatus.NOT_VERIFIED,
                    f"varios candidatos igualmente plausibles ({', '.join(sorted(dois)[:3])})",
                    kind="ambiguous",
                )
            rec = cands[0]
            sess.cache.put(rec.doi, rec)
    except Unavailable as exc:
        return ReferenceOutcome(
            CriterionStatus.NOT_VERIFIED, f"servicio no disponible: {exc}", kind="unavailable"
        )

    issues = _compare(src, rec, cfg)
    if issues:
        return ReferenceOutcome(
            CriterionStatus.FAILED, "; ".join(issues), rec.doi, rec.provider, kind="mismatch"
        )
    return ReferenceOutcome(
        CriterionStatus.PASSED, "existe y coincide", rec.doi, rec.provider,
        source=_enrich(src, rec),
    )


def open_session(
    cfg: ResolverConfig = ResolverConfig(),
    *,
    fetch: Fetch = _default_fetch,
    cache: Optional[PositiveCache] = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
    metrics: ResolverMetrics = GATE_METRICS,
    user_agent: str = "AlejandrIA-PublicationGate/1.0",
) -> _Session:
    """Sesión del resolver con la identidad de salida y las métricas de quien la pide."""
    return _Session(cfg, fetch, sleep, clock, cache or PositiveCache(cfg.cache_ttl_days),
                    metrics, user_agent)


async def resolve_reference(sess: _Session, src: dict) -> ReferenceOutcome:
    """Resuelve **una** referencia (DOI, o título y autores) con su causa estructurada."""
    return await _resolve_one(sess, src)


def _enrich(src: dict, rec: Canonical) -> dict:
    """Completa la fuente con los metadatos canónicos sin pisar lo que ya trae."""
    out = dict(src)
    out["doi"] = rec.doi
    if not str(out.get("year", "")).strip() and rec.year:
        out["year"] = str(rec.year)
    if not str(out.get("journal", "")).strip() and rec.journal:
        out["journal"] = rec.journal
    if not str(out.get("authors", "")).strip() and rec.authors:
        out["authors"] = ", ".join(rec.authors)
    return out


async def check_reference_existence(
    sources: Iterable[dict[str, Any]],
    cfg: ResolverConfig = ResolverConfig(),
    *,
    fetch: Fetch = _default_fetch,
    cache: Optional[PositiveCache] = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[CriterionResult, list[dict]]:
    """Resuelve cada fuente citable. Devuelve el criterio y las fuentes enriquecidas.

    Una fuente `passed` vuelve con DOI, año, revista y autores completados desde el
    registro canónico (AC2/AC3: se resuelve y enriquece *antes* de validar la
    estructura). Las demás vuelven tal cual.
    """
    sess = _Session(cfg, fetch, sleep, clock, cache or PositiveCache(cfg.cache_ttl_days))
    enriched: list[dict] = []
    evidence: list[dict] = []
    worst = CriterionStatus.PASSED
    index = 0
    for src in sources or []:
        if not is_citable(src):
            enriched.append(src)
            continue
        index += 1
        if sess.expired():
            out = ReferenceOutcome(CriterionStatus.NOT_VERIFIED, "tiempo máximo de evaluación agotado")
        else:
            out = await _resolve_one(sess, src)
        enriched.append(out.source or src)
        observe_gate_reference(
            "resolved" if out.status is CriterionStatus.PASSED
            else "mismatch" if out.status is CriterionStatus.FAILED
            else "not_verified"
        )
        if out.status is not CriterionStatus.PASSED:
            evidence.append(
                {
                    "index": index,
                    "title": str(src.get("title", "")) or "(sin título)",
                    "status": out.status.value,
                    "reason": out.reason,
                }
            )
            # `failed` pesa más que `not_verified`: ambos bloquean, pero una
            # referencia inventada no es lo mismo que una que no se pudo comprobar.
            if out.status is CriterionStatus.FAILED:
                worst = CriterionStatus.FAILED
            elif worst is CriterionStatus.PASSED:
                worst = CriterionStatus.NOT_VERIFIED
    return CriterionResult(CRITERION, worst, evidence), enriched
