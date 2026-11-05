"""Progreso por unidades de trabajo reales (SPEC-030 / T18.4 / AC5).

AC5 permite progreso fraccional **solo** si el agente emite unidades reales, y
prohíbe explícitamente derivarlo de tokens emitidos o de tiempo transcurrido.

Lo que se observa aquí es un hecho: cuando aparece el encabezado de la cuarta
sección, la cuarta ha empezado. Quien no pueda decir eso de su trabajo no emite
nada y la interfaz lo muestra indeterminado.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.platform.progress import (  # noqa: E402
    SECCIONES_EN, SECCIONES_ES, SectionTracker, seccion_en_curso, secciones_para,
)


# ── Detección de sección ────────────────────────────────────────────────────

def test_sin_texto_no_hay_seccion():
    """Antes del primer encabezado no se afirma nada."""
    assert seccion_en_curso("", SECCIONES_ES) is None
    assert seccion_en_curso("texto suelto sin encabezados", SECCIONES_ES) is None


def test_detecta_la_seccion_por_su_encabezado():
    assert seccion_en_curso("## Resumen\nalgo", SECCIONES_ES) == 1
    assert seccion_en_curso("## Resumen\n## Introducción\n", SECCIONES_ES) == 2


def test_tolera_tildes_mayusculas_y_numeracion():
    """El modelo escribe el encabezado como le da; el progreso no puede depender de eso."""
    assert seccion_en_curso("### 3. METODOLOGÍA", SECCIONES_ES) == 3
    assert seccion_en_curso("## Metodologia y datos", SECCIONES_ES) == 3
    assert seccion_en_curso("#  discusión final", SECCIONES_ES) == 5


def test_no_retrocede_si_se_menciona_una_seccion_anterior():
    """Una barra que va hacia atrás se lee como un fallo.

    El modelo puede abrir «## Discusión» y dentro escribir «## Introducción» al
    recapitular; quedarse con la última encontrada haría retroceder el contador.
    """
    texto = "## Resumen\n## Introducción\n## Metodología\n## Discusión\n## Introducción\n"
    assert seccion_en_curso(texto, SECCIONES_ES) == 5


def test_funciona_en_ingles():
    assert seccion_en_curso("## Methodology", SECCIONES_EN) == 3
    assert secciones_para("en") == SECCIONES_EN
    assert secciones_para("es") == SECCIONES_ES


def test_un_encabezado_desconocido_no_cuenta():
    assert seccion_en_curso("## Agradecimientos", SECCIONES_ES) is None


def test_el_texto_sin_formato_markdown_no_dispara():
    """«Resumen» en mitad de un párrafo no es el comienzo del resumen."""
    assert seccion_en_curso("en el resumen se explica que...", SECCIONES_ES) is None


# ── El seguimiento sobre un flujo de tokens ─────────────────────────────────

def test_avisa_solo_cuando_cambia_la_seccion():
    """Emitir por token convertiría el progreso en ruido."""
    t = SectionTracker("es")
    assert t.feed("## Resumen\n") == 1
    assert t.feed("texto del ") is None
    assert t.feed("resumen\n") is None
    assert t.feed("## Introducción\n") == 2


def test_el_total_es_el_numero_de_secciones():
    assert SectionTracker("es").total == len(SECCIONES_ES)


def test_reconstruye_un_encabezado_partido_entre_tokens():
    """El streaming parte las palabras; el encabezado llega a trozos."""
    t = SectionTracker("es")
    nueva = None
    for trozo in ["##", " Meto", "dolo", "gía", "\n"]:
        resultado = t.feed(trozo)
        if resultado is not None:
            nueva = resultado
    assert nueva == 3


def test_el_avance_es_monotono():
    t = SectionTracker("es")
    for trozo in ["## Resumen\n", "## Discusión\n", "## Introducción\n"]:
        t.feed(trozo)
    assert t.current == 5, "no puede volver atrás"


def test_sin_encabezados_nunca_emite():
    """Un agente que no sabe sus unidades no inventa ninguna."""
    t = SectionTracker("es")
    for trozo in ["hola ", "esto ", "es ", "texto ", "corrido"]:
        assert t.feed(trozo) is None
    assert t.current == 0


# ── La prohibición de AC5, hecha test ───────────────────────────────────────

def test_el_progreso_no_depende_de_cuantos_tokens_van():
    """Mil tokens sin encabezado siguen siendo «no sé en qué sección voy».

    Es la prohibición de AC5 en forma de test: si alguien sustituyera esto por
    una cuenta de tokens, este caso fallaría.
    """
    t = SectionTracker("es")
    for _ in range(1000):
        t.feed("palabra ")
    assert t.current == 0


def test_el_progreso_no_depende_del_tiempo():
    """Dos seguimientos con el mismo texto dan lo mismo, se tarde lo que se tarde."""
    uno, otro = SectionTracker("es"), SectionTracker("es")
    uno.feed("## Resumen\n## Introducción\n")
    for trozo in ["## Resumen\n", "## Introducción\n"]:
        otro.feed(trozo)
    assert uno.current == otro.current == 2
