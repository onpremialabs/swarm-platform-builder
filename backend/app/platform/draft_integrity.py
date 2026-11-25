"""Detección de borradores truncados (SPEC-036 / T24.9 / AC10).

Un modelo que se queda sin presupuesto de salida no da error: devuelve lo que llevaba, con
una respuesta HTTP 200. En una prueba de punta a punta con `qwen3.5:9b` el borrador acabó en
«…métricas como el tiempo de», sin Discusión, y siguió al Revisor y al Publicador como si
estuviera entero. Esto es lo que lo distingue.

Dos señales, en este orden de confianza:

1. **El motivo de parada del proveedor** (`length` / `max_tokens`): lo declara quien cortó, no
   se infiere. Si lo dice, es truncado y no hace falta mirar el texto.
2. **Una heurística determinista** para cuando el proveedor no lo dice (un doble de pruebas,
   una pasarela que no lo propaga): faltan secciones obligatorias del IMRaD o el texto acaba
   sin cierre de frase.

La heurística **no se aplica cuando el proveedor declaró un motivo de parada distinto de
truncado**: si dijo `stop`, el modelo terminó por su voluntad y un final raro es estilo, no
corte. Es una función pura: no llama a nadie y se prueba sin pipeline.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.platform.llm import MOTIVOS_TRUNCADO

#: Secciones obligatorias del manuscrito, por idioma: alternativas por sección (el modelo puede
#: llamar «Metodología» a «Métodos»). Coinciden con las que pide el prompt del Redactor.
SECCIONES_IMRAD = {
    "es": (
        ("Resumen", ("resumen", "abstract")),
        ("Introducción", ("introducción", "introduccion")),
        ("Metodología", ("metodología", "metodologia", "métodos", "metodos", "materiales y métodos")),
        ("Resultados", ("resultados",)),
        ("Discusión", ("discusión", "discusion")),
    ),
    "en": (
        ("Abstract", ("abstract", "resumen")),
        ("Introduction", ("introduction", "introducción")),
        ("Methodology", ("methodology", "methods", "materials and methods", "metodología")),
        ("Results", ("results", "resultados")),
        ("Discussion", ("discussion", "discusión")),
    ),
}

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


def missing_sections(texto: str, language: str = "es") -> List[str]:
    """Secciones obligatorias del IMRaD que el texto no tiene como encabezado."""
    titulos = _titulos(texto)
    faltan = []
    for nombre, alternativas in SECCIONES_IMRAD.get((language or "es").lower(), SECCIONES_IMRAD["es"]):
        if not any(t == alt or t.startswith(alt) for t in titulos for alt in alternativas):
            faltan.append(nombre)
    return faltan


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
    language: str = "es",
    require_sections: bool = True,
) -> Optional[Dict[str, object]]:
    """Devuelve el diagnóstico si el texto está truncado, o `None` si parece entero.

    ``require_sections=False`` para plantillas propias de la persona usuaria, que pueden pedir
    otra estructura: entonces solo cuentan el motivo de parada y el cierre de frase.
    """
    motivo = (stop_reason or "").lower() or None
    if motivo in MOTIVOS_TRUNCADO:
        return {"signal": "stop_reason", "stop_reason": motivo, "words": len((texto or "").split())}
    if motivo is not None:
        return None  # El proveedor dijo que terminó por su voluntad.

    razones = []
    faltan: List[str] = []
    if not (texto or "").strip():
        razones.append("empty")
    else:
        if require_sections:
            faltan = missing_sections(texto, language)
            if faltan:
                razones.append("missing_sections")
        if ends_mid_sentence(texto):
            razones.append("unterminated_sentence")
    if not razones:
        return None
    return {
        "signal": "heuristic",
        "stop_reason": None,
        "reasons": razones,
        "missing_sections": faltan,
        "words": len((texto or "").split()),
        "tail": (texto or "").rstrip()[-80:],
    }


def describe(diagnostico: Dict[str, object]) -> str:
    """Frase para el log y el mensaje de error: qué señal detectó el corte."""
    if diagnostico.get("signal") == "stop_reason":
        return f"el proveedor cortó por límite de salida (motivo de parada «{diagnostico['stop_reason']}»)"
    partes = []
    if "missing_sections" in (diagnostico.get("reasons") or []):
        partes.append("faltan secciones obligatorias: " + ", ".join(diagnostico["missing_sections"]))  # type: ignore[arg-type]
    if "unterminated_sentence" in (diagnostico.get("reasons") or []):
        partes.append(f"el texto acaba sin cierre de frase («…{diagnostico.get('tail', '')[-40:]}»)")
    if "empty" in (diagnostico.get("reasons") or []):
        partes.append("el texto está vacío")
    return "; ".join(partes) or "señal de truncado"
