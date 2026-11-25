"""Detección de borradores truncados (SPEC-036 / T24.9 / AC10 y T24.10 / AC11).

Un modelo que se queda sin presupuesto de salida no da error: devuelve lo que llevaba, con
una respuesta HTTP 200. En una prueba de punta a punta con `qwen3.5:9b` el borrador acabó en
«…métricas como el tiempo de», sin Discusión, y siguió al Revisor y al Publicador como si
estuviera entero. Y con `num_ctx=16384` acabó en «(HarnessDev, 2024», sin Discusión, **con
parada normal**: el proveedor no vio corte alguno. Por eso:

* **La heurística se aplica siempre** (AC11): faltan secciones obligatorias o el texto acaba
  sin cierre de frase. No depende de lo que diga el proveedor.
* **El motivo de parada solo añade una señal**: si es de corte (`length` / `max_tokens`) se
  suma `stop_reason` a `signals` y manda como `signal` principal; si es una parada normal no
  exculpa al texto.

Las secciones obligatorias **no están en este módulo**: salen de `gate.structure`
(`sections` + `titles` por idioma) de la plantilla del proyecto, y un título vale si está en
**cualquiera** de los idiomas declarados (una variante o un idioma distinto al configurado no
es un falso positivo). Quien llama las resuelve con `required_sections(...)`. Sin
plantilla/compuerta no hay secciones que exigir y solo cuenta el cierre de frase.

`references` no se exige al Redactor (`SECCIONES_FUERA_DEL_REDACTOR`): la lista de
referencias la construye el Formateador en código a partir de las fuentes y el prompt del
Redactor no la pide.

Es una función pura: no llama a nadie y se prueba sin pipeline.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.platform.llm import MOTIVOS_TRUNCADO

#: Secciones del `gate.structure` que **no** escribe el Redactor: las añade un paso posterior.
SECCIONES_FUERA_DEL_REDACTOR = frozenset({"references"})

#: Una sección obligatoria: (clave de la plantilla, títulos aceptados ya normalizados).
Seccion = Tuple[str, Tuple[str, ...]]


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"^[\d.\s)\-]+", "", t)
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def required_sections(gate: Any) -> List[Seccion]:
    """Secciones que debe traer el borrador según `gate.structure` (duck-typing de `GateConfig`).

    Cada una acepta los títulos de **todos** los idiomas declarados. `[]` si no hay compuerta
    o no declara títulos.
    """
    if gate is None:
        return []
    titulos = getattr(gate, "titles", None) or {}
    resultado: List[Seccion] = []
    for clave in getattr(gate, "sections", ()) or ():
        if clave in SECCIONES_FUERA_DEL_REDACTOR:
            continue
        aceptados = tuple(sorted({_norm(t) for por_idioma in titulos.values()
                                  for t in (por_idioma.get(clave) or ()) if _norm(t)}))
        if aceptados:
            resultado.append((clave, aceptados))
    return resultado


#: Cómo puede acabar un texto entero: puntuación de cierre, con cierres de comillas/paréntesis/
#: énfasis/cita `[F1]` detrás.
_CIERRE = re.compile(r"""[.!?…:;。]["'”’)\]*_»`]*(\s*\[[^\]]*\])*["'”’)\]*_»`]*$""")
#: Una última línea que no es prosa (lista, tabla, cita, bloque de código, encabezado) no
#: termina en punto sin que eso signifique corte: la ausencia de secciones cubre ese caso.
_NO_PROSA = re.compile(r"^\s*([-*+>|#]|\d+[.)]\s|```)")


def _titulos(texto: str) -> List[str]:
    """Líneas que funcionan como encabezado: `# …`, o una línea corta en negrita o sola."""
    encontrados = []
    for linea in texto.splitlines():
        limpia = linea.strip().strip("#*_ ").rstrip(":").strip().lower()
        if not limpia:
            continue
        if linea.lstrip().startswith("#") or (len(limpia) <= 60 and (
            linea.strip().startswith(("**", "__")) or re.match(r"^\d+[.)]?\s", linea.strip())
        )):
            encontrados.append(re.sub(r"^\d+[.)]?\s+", "", limpia))
    return encontrados


def missing_sections(texto: str, sections: Sequence[Seccion]) -> List[str]:
    """Claves de las secciones obligatorias que el texto no tiene como encabezado.

    Un encabezado que junta dos («Resultados y Discusión») cuenta para las dos: que estén
    fundidas lo juzga la compuerta, no es un corte.
    """
    presentes = set()
    for titulo in _titulos(texto):
        norm = _norm(titulo)
        trozos = [norm] + [p.strip() for p in re.split(r"\s+(?:y|and)\s+", norm) if p.strip()]
        for clave, aceptados in sections:
            if any(t == a or t.startswith(a + " ") for t in trozos for a in aceptados):
                presentes.add(clave)
    return [clave for clave, _ in sections if clave not in presentes]


def ends_mid_sentence(texto: str) -> bool:
    """¿La última línea de prosa acaba sin cierre de frase?"""
    lineas = [l for l in texto.rstrip().splitlines() if l.strip()]
    if not lineas:
        return True
    ultima = lineas[-1].rstrip()
    if _NO_PROSA.match(ultima):
        return False
    return not _CIERRE.search(ultima)


def detect_truncation(
    texto: str,
    stop_reason: Optional[str] = None,
    *,
    sections: Sequence[Seccion] = (),
) -> Optional[Dict[str, object]]:
    """Devuelve el diagnóstico si el texto está truncado, o `None` si parece entero.

    ``sections`` son las obligatorias (`required_sections`); vacío para plantillas propias o
    redacciones con esquema del autor, que pueden pedir otra estructura: entonces cuenta solo
    el cierre de frase (y el motivo de parada de corte).
    """
    motivo = (stop_reason or "").lower() or None
    corte = motivo in MOTIVOS_TRUNCADO
    razones: List[str] = []
    faltan: List[str] = []
    if not (texto or "").strip():
        razones.append("empty")
    else:
        faltan = missing_sections(texto, sections) if sections else []
        if faltan:
            razones.append("missing_sections")
        if ends_mid_sentence(texto):
            razones.append("unterminated_sentence")
    if not razones and not corte:
        return None
    señales = (["stop_reason"] if corte else []) + (["heuristic"] if razones else [])
    return {
        "signal": señales[0],
        "signals": señales,
        "stop_reason": motivo,
        "reasons": razones,
        "missing_sections": faltan,
        "words": len((texto or "").split()),
        "tail": (texto or "").rstrip()[-80:],
    }


def describe(diagnostico: Dict[str, object]) -> str:
    """Frase para el log y el mensaje de error: qué señal detectó el corte."""
    partes = []
    if "stop_reason" in (diagnostico.get("signals") or [diagnostico.get("signal")]):
        partes.append(f"el proveedor cortó por límite de salida (motivo de parada «{diagnostico['stop_reason']}»)")
    if "missing_sections" in (diagnostico.get("reasons") or []):
        partes.append("faltan secciones obligatorias: " + ", ".join(diagnostico["missing_sections"]))  # type: ignore[arg-type]
    if "unterminated_sentence" in (diagnostico.get("reasons") or []):
        partes.append(f"el texto acaba sin cierre de frase («…{diagnostico.get('tail', '')[-40:]}»)")
    if "empty" in (diagnostico.get("reasons") or []):
        partes.append("el texto está vacío")
    return "; ".join(partes) or "señal de truncado"
