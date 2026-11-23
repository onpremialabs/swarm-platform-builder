#!/usr/bin/env python3
"""Controles de i18n del frontend (SPEC-041 / T29.13 / AC7 + AC11).

Dos controles, los dos stdlib y los dos en la CI (los ejecuta
`backend/tests/test_i18n_checks.py`, dentro del job `Backend · pytest`):

1. **Paridad de catálogos (AC7).** Para cada espacio de nombres, los catálogos
   `es.json` / `en.json` de un directorio `i18n/` deben:
   * tener las mismas claves (las formas plurales `clave_one`, `clave_other`, ...
     cuentan como la misma clave: cada idioma tiene las suyas);
   * usar las mismas variables de interpolación `{nombre}` en cada clave;
   * no traer claves **sin usar**: una clave cuenta como usada si aparece como
     cadena (`'clave'` o `'espacio:clave'`) en el código, o si cuelga de un prefijo
     dinámico (`` `estado.${x}` ``).
   Un `en.json` ausente se trata como catálogo vacío: con catálogos vacíos el
   control pasa de forma vacía; en cuanto hay claves en es y no en en, falla.

2. **Literales nuevos en `.jsx` (AC11).** Detecta texto fijo en JSX (texto entre
   etiquetas, atributos `title`/`placeholder`/`aria-label`/`alt`/`label`/... y
   `{'texto'}`) y falla indicando **archivo y línea** si aparece uno que no está
   en la línea base ni en la lista de excepciones.

   * `scripts/i18n_literals_baseline.json` — la **deuda**: los literales que ya
     existían cuando se creó el control (por fichero y texto, con recuento). Solo
     puede **bajar**: T29.7/T29.8 extraen cadenas a los catálogos y la vacían. Un
     literal nuevo falla; una entrada de la línea base que ya no existe también
     falla (hasta que se regenere con `--update`), para que la deuda no se pueda
     reusar para esconder literales nuevos.
   * `scripts/i18n_literals_exceptions.json` — excepciones **permanentes y
     revisables**, cada una con su motivo (marcas, símbolos, ficheros).

Uso:
    python scripts/check_i18n.py                  # ambos controles
    python scripts/check_i18n.py --update         # reduce la línea base (nunca la amplía)
    python scripts/check_i18n.py --init-baseline  # la genera desde cero (solo bootstrap)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FUENTE = RAIZ / "frontend" / "src"
BASELINE = RAIZ / "scripts" / "i18n_literals_baseline.json"
EXCEPCIONES = RAIZ / "scripts" / "i18n_literals_exceptions.json"

IDIOMAS = ("es", "en")
SUFIJOS_PLURAL = ("zero", "one", "two", "few", "many", "other")
VARIABLE = re.compile(r"\{(\w+)\}")

# ── Paridad ──────────────────────────────────────────────────────────────────


def _aplanar(obj, prefijo: str = "", salida: dict | None = None) -> dict[str, str]:
    salida = {} if salida is None else salida
    for k, v in (obj or {}).items():
        clave = f"{prefijo}.{k}" if prefijo else k
        if isinstance(v, dict):
            _aplanar(v, clave, salida)
        else:
            salida[clave] = str(v)
    return salida


def _base(clave: str) -> str:
    """`items_one` -> `items`: las formas plurales son la misma clave."""
    m = re.fullmatch(r"(.+)_(" + "|".join(SUFIJOS_PLURAL) + ")", clave)
    return m.group(1) if m else clave


def _por_base(catalogo: dict[str, str]) -> dict[str, set[str]]:
    """clave base -> variables de interpolación (unión de sus formas plurales)."""
    out: dict[str, set[str]] = {}
    for clave, texto in catalogo.items():
        out.setdefault(_base(clave), set()).update(VARIABLE.findall(texto))
    return out


def cargar_catalogos(fuente: Path = FUENTE) -> dict[str, dict[str, dict[str, str]]]:
    """espacio -> idioma -> clave plana -> texto, desde cada `i18n/{es,en}.json`."""
    catalogos: dict[str, dict[str, dict[str, str]]] = {}
    for directorio in sorted(fuente.rglob("i18n")):
        if not directorio.is_dir():
            continue
        ficheros = {i: directorio / f"{i}.json" for i in IDIOMAS}
        if not any(f.exists() for f in ficheros.values()):
            continue
        indice = directorio / "index.js"
        espacio = "platform"
        if indice.exists():
            m = re.search(r"NAMESPACE\s*=\s*['\"]([^'\"]+)['\"]", indice.read_text(encoding="utf-8"))
            if m:
                espacio = m.group(1)
        catalogos[espacio] = {
            i: _aplanar(json.loads(f.read_text(encoding="utf-8"))) if f.exists() else {}
            for i, f in ficheros.items()
        }
    return catalogos


def _literales_de_codigo(fuente: Path) -> tuple[set[str], list[str]]:
    """Cadenas del código (sin tests) y prefijos de plantillas dinámicas."""
    cadenas: set[str] = set()
    prefijos: list[str] = []
    patron = re.compile(r"""(['"`])((?:\\.|(?!\1)[^\\])*)\1""", re.S)
    for f in fuente.rglob("*"):
        if f.suffix not in (".js", ".jsx", ".mjs") or ".test." in f.name:
            continue
        for m in patron.finditer(f.read_text(encoding="utf-8")):
            texto = m.group(2)
            if m.group(1) == "`" and "${" in texto:
                prefijos.append(texto.split("${", 1)[0])
            else:
                cadenas.add(texto)
    return cadenas, [p for p in prefijos if p]


def comprobar_paridad(
    catalogos: dict[str, dict[str, dict[str, str]]],
    cadenas: set[str],
    prefijos: list[str],
) -> list[str]:
    """Devuelve los fallos (vacío = todo bien)."""
    fallos: list[str] = []
    for espacio, por_idioma in sorted(catalogos.items()):
        vistas = {i: _por_base(por_idioma.get(i, {})) for i in IDIOMAS}
        todas = set().union(*(set(v) for v in vistas.values()))
        for clave in sorted(todas):
            for i in IDIOMAS:
                if clave not in vistas[i]:
                    otro = next(o for o in IDIOMAS if clave in vistas[o])
                    fallos.append(
                        f"[{espacio}] la clave '{clave}' existe en '{otro}' y falta en '{i}'"
                    )
            if all(clave in vistas[i] for i in IDIOMAS):
                es_v, en_v = vistas["es"][clave], vistas["en"][clave]
                if es_v != en_v:
                    fallos.append(
                        f"[{espacio}] la clave '{clave}' difiere en variables de interpolación: "
                        f"faltan en 'en' {sorted(es_v - en_v)}, faltan en 'es' {sorted(en_v - es_v)}"
                    )
            completa = f"{espacio}:{clave}"
            usada = (
                clave in cadenas
                or completa in cadenas
                or any(clave.startswith(p) or completa.startswith(p) for p in prefijos)
            )
            if not usada:
                fallos.append(f"[{espacio}] la clave '{clave}' no se usa en el código")
    return fallos


# ── Literales ────────────────────────────────────────────────────────────────

ATRIBUTOS = r"(?:title|placeholder|aria-label|aria-description|aria-placeholder|alt|label|description|helperText|emptyText)"
COMENTARIO = re.compile(r"/\*.*?\*/|(?<![:\"'`\w])//[^\n]*", re.S)
LETRA = re.compile(r"[A-Za-zÀ-ÿ]")
# texto entre etiquetas: `>` que no cierra una flecha/comparación, sin `{`, `}`, `<`
TEXTO_JSX = re.compile(r"(?<![=\-])>([^<>{}]+)(?=<)")
ATRIBUTO = re.compile(r"\b" + ATRIBUTOS + r"""\s*=\s*(?:"([^"]*)"|'([^']*)')""")
EXPRESION = re.compile(r"""\{\s*(?:'([^'\n]*)'|"([^"\n]*)"|`([^`$\n]*)`)\s*\}""")


def _blanquear(m: re.Match) -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def literales_de(texto: str) -> list[tuple[int, str]]:
    """(línea, texto) de cada literal visible en un `.jsx`."""
    limpio = COMENTARIO.sub(_blanquear, texto)
    encontrados: list[tuple[int, str]] = []

    def _linea(pos: int) -> int:
        return limpio.count("\n", 0, pos) + 1

    for m in TEXTO_JSX.finditer(limpio):
        t = _normalizar(m.group(1))
        if LETRA.search(t) and not re.search(r"&&|\|\||=>|;", t):
            # la línea es la del primer carácter no blanco, no la de la etiqueta
            desfase = len(m.group(1)) - len(m.group(1).lstrip())
            encontrados.append((_linea(m.start(1) + desfase), t))
    for m in ATRIBUTO.finditer(limpio):
        t = _normalizar(m.group(1) if m.group(1) is not None else m.group(2))
        if LETRA.search(t):
            encontrados.append((_linea(m.start()), t))
    for m in EXPRESION.finditer(limpio):
        t = _normalizar(next(g for g in m.groups() if g is not None))
        if LETRA.search(t):
            encontrados.append((_linea(m.start()), t))
    return sorted(encontrados)


def _ficheros_jsx(fuente: Path) -> list[Path]:
    return [f for f in sorted(fuente.rglob("*.jsx")) if ".test." not in f.name]


def cargar_excepciones(ruta: Path = EXCEPCIONES) -> dict:
    if not ruta.exists():
        return {"textos": {}, "ficheros": {}}
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return {"textos": datos.get("textos", {}), "ficheros": datos.get("ficheros", {})}


def literales_actuales(fuente: Path = FUENTE, excepciones: dict | None = None):
    """fichero relativo -> [(línea, texto)], sin lo exento."""
    exc = excepciones if excepciones is not None else cargar_excepciones()
    out: dict[str, list[tuple[int, str]]] = {}
    for f in _ficheros_jsx(fuente):
        rel = f.relative_to(fuente).as_posix()
        if rel in exc["ficheros"]:
            continue
        lits = [
            (n, t) for n, t in literales_de(f.read_text(encoding="utf-8"))
            if t not in exc["textos"]
        ]
        if lits:
            out[rel] = lits
    return out


def _baseline_de(actuales) -> dict[str, dict[str, int]]:
    return {
        rel: dict(sorted(Counter(t for _, t in lits).items()))
        for rel, lits in sorted(actuales.items())
    }


def cargar_baseline(ruta: Path = BASELINE) -> dict[str, dict[str, int]]:
    if not ruta.exists():
        return {}
    return json.loads(ruta.read_text(encoding="utf-8")).get("ficheros", {})


def comparar_literales(actuales, baseline) -> tuple[list[str], list[str]]:
    """(nuevos, obsoletos): nuevos con archivo:línea; obsoletos = deuda ya pagada."""
    nuevos: list[str] = []
    obsoletos: list[str] = []
    for rel, lits in actuales.items():
        permitido = Counter(baseline.get(rel, {}))
        for linea, texto in lits:
            if permitido[texto] > 0:
                permitido[texto] -= 1
            else:
                nuevos.append(f"frontend/src/{rel}:{linea}  texto literal nuevo: {texto!r}")
    for rel, textos in baseline.items():
        hoy = Counter(t for _, t in actuales.get(rel, []))
        for texto, n in textos.items():
            if hoy[texto] < n:
                obsoletos.append(f"{rel}: {texto!r} (línea base {n}, hoy {hoy[texto]})")
    return nuevos, obsoletos


def _escribir_baseline(actuales, ruta: Path = BASELINE) -> int:
    datos = _baseline_de(actuales)
    total = sum(sum(v.values()) for v in datos.values())
    ruta.write_text(
        json.dumps(
            {
                "_comentario": (
                    "Deuda de literales JSX previa al control (T29.13). Solo puede bajar: "
                    "T29.7/T29.8 la vacían al extraer cadenas. Regenerar con "
                    "`python scripts/check_i18n.py --update`."
                ),
                "total": total,
                "ficheros": datos,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    return total


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Controles de i18n del frontend")
    ap.add_argument("--update", action="store_true", help="reduce la línea base (nunca la amplía)")
    ap.add_argument("--init-baseline", action="store_true", help="genera la línea base desde cero")
    args = ap.parse_args()

    actuales = literales_actuales()
    if args.init_baseline:
        print(f"[OK] línea base creada: {_escribir_baseline(actuales)} literales")
        return 0
    baseline = cargar_baseline()
    nuevos, obsoletos = comparar_literales(actuales, baseline)
    if args.update:
        if nuevos:
            print("[FALLO] hay literales nuevos; la línea base no se amplía. Extráelos a los catálogos:")
            print("\n".join(f"  {n}" for n in nuevos))
            return 1
        print(f"[OK] línea base reducida a {_escribir_baseline(actuales)} literales")
        return 0

    fallos = comprobar_paridad(cargar_catalogos(), *_literales_de_codigo(FUENTE))
    codigo = 0
    if fallos:
        codigo = 1
        print(f"[FALLO] paridad de catálogos ({len(fallos)}):")
        print("\n".join(f"  {f}" for f in fallos))
    if nuevos:
        codigo = 1
        print(f"[FALLO] literales nuevos en .jsx ({len(nuevos)}); usa t('clave') y el catálogo:")
        print("\n".join(f"  {n}" for n in nuevos))
    if obsoletos:
        codigo = 1
        print(f"[FALLO] la línea base tiene deuda ya pagada ({len(obsoletos)}); ejecuta --update:")
        print("\n".join(f"  {o}" for o in obsoletos))
    if codigo == 0:
        deuda = sum(sum(v.values()) for v in baseline.values())
        print(f"[OK] paridad de catálogos; sin literales nuevos (deuda en línea base: {deuda}).")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
