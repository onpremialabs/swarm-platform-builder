"""Cliente HTTP con reintentos para las bases bibliográficas (SPEC-034 / AC1, AC10).

Toda petición sale por `egress.safe_get(quien="literature_discovery")`; este módulo no
abre ningún cliente HTTP propio (hay un test estructural que lo vigila).

Transitorio (se reintenta con espera exponencial): tiempo agotado, error de red, 429,
5xx y respuesta que no se puede interpretar. No transitorio (falla a la primera): un
destino bloqueado por la guarda de egress y cualquier otro 4xx, que repetir no arregla.
Al agotar los reintentos se levanta `SourceError`, con la causa y los intentos.
"""
from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx

from app.platform.egress import QUIEN_LITERATURA, EgressBlocked

logger = logging.getLogger(__name__)

Fetch = Callable[..., Awaitable[Any]]
Sleep = Callable[[float], Awaitable[None]]

USER_AGENT = "AlejandrIA-LiteratureDiscovery/1.0"


class SourceError(Exception):
    """Una base no dio una respuesta utilizable. Lleva su nombre y la causa."""

    def __init__(self, db: str, kind: str, detail: str, attempts: int):
        self.db, self.kind, self.detail, self.attempts = db, kind, detail, attempts
        super().__init__(f"{db}: {detail} (tras {attempts} intento(s))")


@dataclass(frozen=True)
class LiteratureConfig:
    timeout_s: float = 10.0
    retries: int = 2
    backoff_s: float = 1.0
    max_backoff_s: float = 30.0
    max_results: int = 10
    contact_email: str = ""
    semantic_scholar_key: str = ""
    ncbi_key: str = ""

    @classmethod
    def from_settings(cls) -> "LiteratureConfig":
        from app.core.config import settings

        return cls(
            timeout_s=settings.LITERATURE_TIMEOUT_S,
            retries=max(0, settings.LITERATURE_RETRIES),
            backoff_s=max(0.0, settings.LITERATURE_BACKOFF_S),
            max_backoff_s=max(0.0, settings.LITERATURE_MAX_BACKOFF_S),
            max_results=max(1, settings.LITERATURE_MAX_RESULTS),
            contact_email=(settings.LITERATURE_CONTACT_EMAIL or "").strip(),
            semantic_scholar_key=(settings.SEMANTIC_SCHOLAR_API_KEY or "").strip(),
            ncbi_key=(settings.NCBI_API_KEY or "").strip(),
        )

    def user_agent(self) -> str:
        # Genérico de la plataforma; el correo es el de contacto configurado por quien
        # opera, nunca el de la persona usuaria.
        return f"{USER_AGENT} (mailto:{self.contact_email})" if self.contact_email else USER_AGENT


async def _default_fetch(url: str, **kwargs: Any) -> httpx.Response:
    # Import tardío: así un test (o un despliegue) que sustituya `egress.safe_get` lo ve.
    from app.platform import egress

    return await egress.safe_get(url, **kwargs)


def _retry_after(response: Any) -> Optional[float]:
    try:
        return max(0.0, float(response.headers.get("retry-after")))
    except (TypeError, ValueError, AttributeError):
        return None


def json_object(response: Any) -> Any:
    """Cuerpo JSON; `ValueError` si no lo es (se trata como respuesta inválida)."""
    try:
        return response.json()
    except ValueError as error:
        raise ValueError("la respuesta no es JSON") from error


def xml_root(response: Any) -> ET.Element:
    """Raíz del XML. Rechaza declaraciones de entidades (expansión de entidades).

    `xml.etree` no es seguro frente a XML hostil y no se puede añadir `defusedxml` sin
    tocar el lock. arXiv y PubMed no necesitan entidades propias; un `DOCTYPE` sin
    `<!ENTITY` (el de `efetch`) sí es legítimo.
    """
    texto = response.text
    if "<!ENTITY" in texto.upper():
        raise ValueError("el XML declara entidades; se rechaza")
    return ET.fromstring(texto)


def json_then(funcion: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Interpreta el JSON **dentro** del bucle de reintentos: una forma inesperada se reintenta."""
    return lambda respuesta: funcion(json_object(respuesta))


def xml_then(funcion: Callable[[ET.Element], Any]) -> Callable[[Any], Any]:
    return lambda respuesta: funcion(xml_root(respuesta))


class ApiSession:
    """Peticiones de **una** base, con reintentos."""

    def __init__(self, db: str, cfg: LiteratureConfig, fetch: Optional[Fetch] = None,
                 sleep: Optional[Sleep] = None):
        self.db, self.cfg = db, cfg
        self._fetch = fetch or _default_fetch
        self._sleep = sleep or asyncio.sleep
        #: Intentos acumulados en esta sesión (para el informe).
        self.attempts = 0

    def headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        return {"User-Agent": self.cfg.user_agent(), **(extra or {})}

    async def request(self, url: str, *, params: Optional[dict] = None,
                      headers: Optional[dict] = None,
                      parse: Callable[[Any], Any] = json_object) -> Any:
        total = self.cfg.retries + 1
        kind, detail = "network", "sin respuesta"
        for intento in range(total):
            self.attempts += 1
            espera: Optional[float] = None
            try:
                respuesta = await self._fetch(
                    url, quien=QUIEN_LITERATURA, params=params,
                    headers=self.headers(headers), timeout=self.cfg.timeout_s,
                )
            except EgressBlocked as error:
                raise SourceError(self.db, "blocked", f"destino bloqueado por egress: {error}",
                                  self.attempts) from error
            except httpx.TimeoutException:
                kind, detail = "timeout", f"tiempo agotado ({self.cfg.timeout_s:g} s)"
            except Exception as error:  # red, TLS, DNS
                kind, detail = "network", f"{type(error).__name__}: {error}"
            else:
                estado = respuesta.status_code
                if estado == 200:
                    try:
                        return parse(respuesta)
                    except (ValueError, KeyError, TypeError, AttributeError, ET.ParseError) as error:
                        kind, detail = "invalid_response", f"respuesta inválida: {error}"
                elif estado == 429:
                    kind, detail = "rate_limited", "límite de tasa (HTTP 429)"
                    espera = _retry_after(respuesta)
                elif estado >= 500:
                    kind, detail = "http_error", f"error del servicio (HTTP {estado})"
                else:
                    # 400/401/403/404...: repetir la misma petición no lo arregla.
                    raise SourceError(self.db, "http_error", f"HTTP {estado}", self.attempts)
            if intento < total - 1:
                pausa = min(self.cfg.max_backoff_s,
                            espera if espera is not None else self.cfg.backoff_s * (2 ** intento))
                logger.info("literature[%s]: %s; reintento %s/%s en %.1f s",
                            self.db, detail, intento + 1, total - 1, pausa)
                await self._sleep(pausa)
        raise SourceError(self.db, kind, detail, self.attempts)
