"""Progreso por unidades de trabajo reales (SPEC-030 / T18.4 / AC5).

El pipeline emite `agent_start` y `token`. Con eso se puede dibujar una barra que
avance, pero no se puede **saber** cuánto falta: un «Redactor 40 %» calculado por
tokens emitidos o por tiempo transcurrido tiene la precisión de un dato y el valor
de una suposición, y la gente toma decisiones con él («le falta poco, espero»).

Lo que sí es un hecho: el Redactor escribe un artículo con secciones conocidas, y
cuando aparece el encabezado de la cuarta, la cuarta ha empezado. Eso no se deriva
de nada, se observa. Es la diferencia entre informar y decorar.

Este módulo no sabe de SSE ni de agentes: recibe texto y devuelve en qué unidad va.
Quien no pueda decir esto de su propio trabajo **no emite nada**, y la interfaz lo
muestra indeterminado, que es la respuesta honesta.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Sequence, Tuple

#: Las secciones del artículo científico, en el orden en que se escriben. Son las
#: mismas que el prompt del Redactor pide, y ese es el punto: si el prompt cambia,
#: esta lista tiene que cambiar con él o el progreso dejará de cuadrar.
SECCIONES_ES: Tuple[str, ...] = (
    "resumen", "introduccion", "metodologia", "resultados", "discusion",
)
SECCIONES_EN: Tuple[str, ...] = (
    "abstract", "introduction", "methodology", "results", "discussion",
)

#: Un encabezado Markdown: lo que el Redactor usa para abrir cada sección.
_ENCABEZADO = re.compile(r"^\s{0,3}#{1,4}\s+(.{1,120})$", re.MULTILINE)


def _normalizar(texto: str) -> str:
    """Sin tildes, sin signos y en minúsculas, para comparar encabezados.

    El modelo escribe «## Metodología», «## METODOLOGIA» o «## 3. Metodología»
    según le da. Comparar el texto crudo haría que el progreso dependiera de esa
    arbitrariedad.
    """
    plano = unicodedata.normalize("NFKD", texto)
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return re.sub(r"[^a-z\s]", " ", plano.lower()).strip()


def secciones_para(idioma: str) -> Tuple[str, ...]:
    return SECCIONES_ES if idioma == "es" else SECCIONES_EN


def seccion_en_curso(texto: str, secciones: Sequence[str]) -> Optional[int]:
    """En qué sección va el texto, 1-indexado. `None` si aún no empezó ninguna.

    Devuelve la **más avanzada** vista hasta ahora y no la última encontrada: el
    modelo puede mencionar «Introducción» dentro de la Discusión, y retroceder el
    contador ahí sería peor que no tenerlo —una barra que va hacia atrás se lee
    como un fallo—.
    """
    if not texto:
        return None

    vistas: List[int] = []
    for encaje in _ENCABEZADO.finditer(texto):
        titulo = _normalizar(encaje.group(1))
        if not titulo:
            continue
        for indice, nombre in enumerate(secciones, start=1):
            # `in` y no igualdad: el encabezado real suele traer numeración o
            # un subtítulo detrás («## 2. Introducción y estado del arte»).
            if nombre in titulo:
                vistas.append(indice)
                break

    return max(vistas) if vistas else None


class SectionTracker:
    """Sigue el avance por secciones de un texto que llega a trozos.

    Guarda el máximo alcanzado y solo avisa cuando **cambia**: emitir un evento
    por token convertiría el progreso en ruido y el cliente tendría que
    deduplicar, que es trabajo que no le toca.
    """

    def __init__(self, idioma: str = "es"):
        self.secciones = secciones_para(idioma)
        self.total = len(self.secciones)
        self._actual = 0
        self._acumulado: List[str] = []

    def feed(self, fragmento: str) -> Optional[int]:
        """Añade un fragmento. Devuelve la sección nueva, o `None` si no cambió."""
        if fragmento:
            self._acumulado.append(fragmento)
        actual = seccion_en_curso("".join(self._acumulado), self.secciones)
        if actual is not None and actual > self._actual:
            self._actual = actual
            return actual
        return None

    @property
    def current(self) -> int:
        return self._actual
