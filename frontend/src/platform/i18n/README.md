# Catálogos del builder (`platform`)

- `es.json` — idioma fuente. Lo registra `main.jsx` con
  `registerMessages('platform', { es: platformEs })`. Las claves se agrupan por
  pantalla o componente (`flows.*`, `agentEditor.*`, `explain.*`, ...) y los plurales
  usan `clave_one` / `clave_other` con la variable `count`.
- `en.json` — **provisional (T29.7)**: copia de `es.json` con los mismos textos en
  español. Existe para que el control de paridad de `scripts/check_i18n.py` (T29.13)
  siga activo: un `en.json` ausente cuenta como catálogo vacío y haría fallar la CI en
  cuanto `es.json` tiene claves. **T29.9 lo sustituye por la traducción**. T29.10 ya lo registra
  en los dos puntos de entrada (`main.jsx` y la revista pública) y añade el selector
  de idioma (`components/ui/LanguageSelector.jsx`): hasta T29.9, elegir inglés cambia
  `<html lang>`, el formato de fechas/números y las cadenas del selector, pero el
  resto del texto sigue en español porque `en.json` es esa copia.
- `rich.js` / `Trans` — mensajes con marcas simples (`<strong>`, `<em>`, `<code>`).
  Se traduce la frase entera, no tres trozos.

Al añadir un texto: crea la clave en `es.json` **y** en `en.json`, pídela con
`t('espacio.clave')` y no concatenes frases (usa `{variable}`). Los tests
`backend/tests/test_platform_i18n_keys.py` y `test_i18n_checks.py` comprueban que cada
clave pedida existe, que las variables del mensaje se pasan y que es/en tienen las
mismas claves.
