"""Presupuesto de una revisión: ventana y tiempo dimensionados por el borrador (SPEC-036 / T24.11 / AC12).

El Revisor llamaba con `timeout=45.0, num_ctx=4096` fijos. Un borrador de 2270 palabras ocupa
más de 4096 tokens: Ollama lo recorta **en silencio** por el principio o por el final y el
modelo puntúa un texto que no vio entero; y 45 s no alcanzan para leerlo, así que el tiempo
agotado se reintentaba cuatro veces con el mismo límite (20 minutos) para repetir el mismo fallo.

Aquí se decide, con una función pura y sin llamar a nadie:

* **la ventana** necesaria = prompt (borrador + rúbrica + instrucciones) + margen de salida,
  redondeada hacia arriba; lo configurado por la cascada (`num_ctx`) es el **mínimo**, y el
  techo es la ventana del modelo (`model_context_window`);
* **el tiempo de espera** = lo configurado (`timeout_seconds`) o, si es mayor, lo que pide el
  tamaño del prompt;
* si el prompt **no cabe** ni en la ventana del modelo, `fits=False`: quien llama no lo envía
  recortado, lo registra y falla cerrado con motivo (`not_verified`).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from app.platform.llm import model_context_window

#: Estimación **conservadora** de tokens: ~3 caracteres por token. El texto en español con los
#: tokenizadores de Qwen/Llama ronda 3,5–4; pecar por exceso solo cuesta algo de ventana, pecar
#: por defecto reintroduce el recorte silencioso.
CARACTERES_POR_TOKEN = 3.0

#: Margen para la respuesta del Revisor (JSON con puntuación y comentarios).
MARGEN_SALIDA_TOKENS = 1024

#: La ventana se pide en múltiplos de esto: evita recargar el modelo por 37 tokens de diferencia.
REDONDEO_VENTANA = 1024

#: Tiempo base y coste por token de prompt (lectura + prefill en un modelo local lento).
TIMEOUT_BASE_SEGUNDOS = 120.0
SEGUNDOS_POR_TOKEN_PROMPT = 0.1

#: Tope al dimensionar solo por tamaño; una persona puede configurar más, y entonces manda.
TIMEOUT_MAXIMO_SEGUNDOS = 1800.0
#: Tope del único reintento tras un tiempo agotado (subir el presupuesto, no repetirlo).
TIMEOUT_MAXIMO_REINTENTO = 3600.0


def estimate_tokens(texto: str) -> int:
    """Tokens estimados de un texto (por exceso)."""
    return math.ceil(len(texto or "") / CARACTERES_POR_TOKEN)


@dataclass(frozen=True)
class ReviewBudget:
    fits: bool
    num_ctx: int
    timeout: float
    prompt_tokens: int
    output_margin: int
    model_window: int

    def as_trace(self) -> Dict[str, Any]:
        datos = asdict(self)
        datos["timeout"] = round(self.timeout, 1)
        return datos


def size_review_budget(
    prompt: str,
    *,
    model: Optional[str],
    configured_ctx: Optional[int] = None,
    configured_timeout: Optional[float] = None,
    output_margin: int = MARGEN_SALIDA_TOKENS,
) -> ReviewBudget:
    """Dimensiona ventana y tiempo para `prompt`. Ver el docstring del módulo."""
    ventana = model_context_window(model)
    tokens = estimate_tokens(prompt)
    necesario = tokens + output_margin
    cabe = necesario <= ventana
    minimo = configured_ctx or 0
    pedido = max(minimo, math.ceil(necesario / REDONDEO_VENTANA) * REDONDEO_VENTANA)
    num_ctx = min(pedido, ventana)

    por_tamano = min(TIMEOUT_BASE_SEGUNDOS + tokens * SEGUNDOS_POR_TOKEN_PROMPT, TIMEOUT_MAXIMO_SEGUNDOS)
    timeout = max(configured_timeout or 0.0, por_tamano)
    return ReviewBudget(
        fits=cabe, num_ctx=num_ctx, timeout=timeout, prompt_tokens=tokens,
        output_margin=output_margin, model_window=ventana,
    )


def raised_timeout(actual: float) -> Optional[float]:
    """Tiempo del único reintento tras agotarse `actual`: el doble, o `None` si no hay más que dar."""
    nuevo = min(actual * 2, max(TIMEOUT_MAXIMO_REINTENTO, actual))
    return nuevo if nuevo > actual else None
