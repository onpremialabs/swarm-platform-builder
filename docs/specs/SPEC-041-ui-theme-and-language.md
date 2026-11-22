# SPEC-041: Tema claro/oscuro e idioma de la interfaz (español / inglés)

- **Estado:** Ready
- **Autor:** Equipo de plataforma (borrador asistido)
- **Fecha:** 2026-11-22
- **Épica:** E29 (GitHub Project)
- **ADR relacionado:** continúa [SPEC-003](SPEC-003-ux-design-system-accessibility.md) (sistema de diseño y accesibilidad; épica E7 cerrada) · respeta la separación `platform/` ↔ `projects/` de [SPEC-013](SPEC-013-structural-refactor-project-independence.md) (T8.6)
- **Severidad:** 🟡

> Pasa a `Ready` por instrucción del equipo; `/speckit-clarify` y
> `/speckit-checklist` quedan pendientes (recomendados por la DoR, no
> bloqueantes).

## 1. Problema

- **El tema oscuro existe en el sistema de diseño pero no en la app.**
  `frontend/ds/colors_and_type.css` declara `[data-theme="dark"], .dark` con tokens
  de marca, superficies y dataviz, y `scripts/check_contrast.py` mide los pares en
  claro y oscuro. Sin embargo, ningún código de `frontend/src/` activa
  `data-theme`: no hay selector, ni preferencia, ni detección del sistema. El
  trabajo de SPEC-003 queda sin usarse.
- **No hay internacionalización.** `package.json` no incluye ninguna librería de
  i18n y los textos están escritos en español dentro del JSX y de los stores
  (p. ej. «Diseña tu pipeline», «Asignar revisor», «Fuentes recuperadas»). Un
  equipo que trabaje en inglés no puede usar la interfaz.
- **Los errores de la API llegan en español** como cadenas en `detail`
  (`core/errors.py`); el cliente las muestra tal cual.
- **No hay preferencias de usuario**: el modelo de usuario no guarda idioma ni
  tema, así que no pueden seguir a la persona entre dispositivos.
- **Hay dos builds Vite** (app principal y revista pública
  `index.public.html`): lo que se haga debe funcionar en ambos.
- **No confundir con el idioma del manuscrito.** El idioma en que se escribe un
  artículo (`es`/`en`, que ya usa la compuerta para los títulos de sección) es un
  dato del artículo y de su brief; esta spec trata solo de la **interfaz**.

## 2. Objetivos / No-objetivos

- **Objetivos:** (a) selector de tema **claro / oscuro / sistema** con
  persistencia y sin parpadeo al cargar; (b) interfaz en **español e inglés** con
  cambio en caliente; (c) preferencia guardada por usuario y también local para
  quien aún no inicia sesión; (d) mensajes de error de la API traducibles; (e)
  garantías en CI: contraste AA en ambos temas y paridad de claves es/en.
- **No-objetivos:** más idiomas (la arquitectura los permite, no se entregan);
  traducir el contenido de los artículos ni los prompts de los agentes; traducción
  automática en tiempo de ejecución; rediseñar el sistema de diseño; que la
  maquetación imprimible del paper (`/articles/:id/paper`) siga el tema de la
  interfaz (se mantiene clara para impresión).

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* un usuario sin preferencia guardada *When* abre la app
  *Then* se aplica el tema del sistema (`prefers-color-scheme`) y el idioma del
  navegador si es `es` o `en`, y `es` en cualquier otro caso.
- [ ] **AC2** — *Given* el selector de tema *When* la persona elige claro, oscuro
  o sistema *Then* `data-theme` de `<html>` cambia al instante, se persiste y, tras
  recargar, la página se pinta **ya con el tema correcto, sin destello del otro**.
- [ ] **AC3** — *Given* el tema oscuro *When* se recorren las pantallas
  (Flow Designer, Artículos, Detalle, Historial, Trazabilidad, Documentos,
  Agentes, Configuración y la revista pública) *Then* no queda ningún componente
  con colores fijos que rompan el contraste, y `check_contrast.py` y
  `check_design_tokens.py` pasan en ambos temas.
- [ ] **AC4** — *Given* el lienzo del Flow Designer y los gráficos *When* cambia
  el tema *Then* nodos, aristas, minimapa y series de datos usan tokens y se leen
  correctamente en ambos.
- [ ] **AC5** — *Given* la vista de maquetación del paper y su impresión *When*
  la interfaz está en oscuro *Then* el documento se mantiene en claro (para
  papel/PDF) y el marco de la página sí respeta el tema.
- [ ] **AC6** — *Given* el selector de idioma *When* se elige español o inglés
  *Then* toda cadena visible de la interfaz cambia sin recargar, `<html lang>` se
  actualiza y fechas, números y plurales usan el formato del idioma (`Intl`).
- [ ] **AC7** — *Given* los catálogos de mensajes *When* se ejecuta el control de
  paridad *Then* falla si una clave existe en un idioma y no en el otro, si hay
  claves sin usar o si falta una variable de interpolación.
- [ ] **AC8** — *Given* el builder (`platform/`) *When* necesita textos del
  proyecto *Then* los obtiene de un **registro** que el proyecto rellena al
  arrancar (como `setAgentCatalog`), sin importar de `projects/`; el test
  `test_frontend_layers.py` sigue pasando.
- [ ] **AC9** — *Given* un usuario autenticado *When* cambia idioma o tema *Then*
  se guarda en su perfil (`PATCH` de preferencias) y se aplica al iniciar sesión en
  otro dispositivo; si la API falla, la preferencia local sigue funcionando.
- [ ] **AC10** — *Given* un error de la API *When* se muestra al usuario *Then* el
  servidor devuelve un **código estable** (`code`) además de `detail`, y el cliente
  muestra el texto del catálogo en el idioma activo; si el código es desconocido,
  muestra `detail` como respaldo.
- [ ] **AC11** — *Given* un cambio que añade texto literal nuevo en un `.jsx` fuera
  de los catálogos *When* corre el control de CI *Then* falla indicando archivo y
  línea (con lista de excepciones revisable).
- [ ] **AC12** — *Given* los selectores *When* se usan con teclado y lector de
  pantalla *Then* son operables, tienen nombre accesible en el idioma activo y
  anuncian el cambio (WCAG 2.1 AA).

## 4. Diseño propuesto

- **Tema:** almacén de preferencias (zustand, como el resto de stores) que escribe
  `data-theme` en `<html>`. Un **script inline** mínimo en `index.html` e
  `index.public.html` lee la preferencia y fija el atributo antes del primer
  pintado para evitar el destello. «Sistema» escucha `matchMedia` y reacciona a
  cambios del sistema operativo.
- **Tokens, no colores:** los componentes que aún usen valores fijos pasan a
  tokens del DS; `scripts/check_design_tokens.py` se extiende para vigilarlo y
  `check_contrast.py` cubre los pares nuevos en los dos temas.
- **i18n:** una librería estándar (propuesta: `i18next` + `react-i18next`, por
  plurales e interpolación) con espacios de nombres: `platform` y uno por
  proyecto. Dependencia nueva sujeta al job `deps-audit` y a la política de
  lock con hashes si se tocara el backend (aquí solo `package.json`).
- **Capas:** `platform/` define `registerMessages(namespace, catalogs)`; el
  proyecto lo invoca desde `main.jsx` como `setAgentCatalog` y compañía.
- **Catálogos:** `src/platform/i18n/{es,en}.json` y
  `src/projects/<slug>/i18n/{es,en}.json`. El español es el idioma fuente.
- **Preferencias en servidor:** columnas `locale` y `theme` en el usuario
  (migración Alembic, nunca SQL a mano) y `PATCH /auth/me/preferences`.
- **Errores:** `core/errors.py` añade `code` estable a las respuestas de error;
  el cliente HTTP (`platform/api/client.js`) las traduce.
- **Control de CI:** script `check_i18n.py` (paridad de claves y variables) y una
  regla/guardia para literales nuevos en JSX; ambos se añaden a `ci.yml`.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Destello de tema incorrecto al cargar | Medio | Script inline previo al render y prueba visual |
| Colores fijos escondidos en componentes y estilos en línea | Alto | Auditoría con el script de tokens; revisión pantalla por pantalla (AC3) |
| Extraer cientos de cadenas introduce regresiones | Medio | Migración por pantallas, con control de paridad y pruebas de humo por ruta |
| Traducciones inconsistentes o de baja calidad | Medio | Glosario común, revisión humana y claves por contexto |
| Mezclar idioma de interfaz con idioma del manuscrito | Medio | Documentado como no-objetivo; campos separados |
| El builder acaba importando del proyecto | Medio | Registro de mensajes y test de capas existente |
| Tamaño del bundle por catálogos | Bajo | Carga diferida del idioma no activo |

## 6. Plan de pruebas

Unitarias del almacén de tema y del selector de idioma; pruebas de los controles
de CI (paridad, literales, contraste, tokens); prueba de integración de
preferencias en servidor con aislamiento por usuario; recorrido manual en las 9
pantallas en 2 temas × 2 idiomas; prueba de teclado y lector de pantalla; ambos
builds (`npm run build` y `npm run build:public`).

## 7. Impacto operativo / observabilidad

Migración aditiva y reversible. Sin impacto en retención de datos (dos campos de
preferencia). Despliegue por pasos: primero tema (bajo riesgo), después
infraestructura i18n y migración gradual de pantallas. Documentar en
`docs/guide/design-system.md` y en la guía del Flow Designer.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E29
  title: "Tema claro/oscuro e idioma de la interfaz (español / inglés)"
  area: area/ux
tasks:
  - id: T29.1
    title: "Almacén de tema claro/oscuro/sistema con data-theme y script previo al render en ambos builds"
    sev: medium
    depends_on: []
    acceptance: [AC1, AC2]
  - id: T29.2
    title: "Selector de tema accesible en la interfaz principal y en la revista pública"
    sev: medium
    depends_on: [T29.1]
    acceptance: [AC2, AC12]
  - id: T29.3
    title: "Auditar y migrar colores fijos a tokens; ampliar check_design_tokens y check_contrast a los pares nuevos"
    sev: high
    depends_on: [T29.1]
    acceptance: [AC3]
  - id: T29.4
    title: "Lienzo del Flow Designer, gráficos y minimapa con tokens en ambos temas"
    sev: medium
    depends_on: [T29.3]
    acceptance: [AC4]
  - id: T29.5
    title: "Maquetación del paper e impresión siempre en claro con el marco según el tema"
    sev: low
    depends_on: [T29.3]
    acceptance: [AC5]
  - id: T29.6
    title: "Infraestructura i18n con espacios de nombres, registro de mensajes por proyecto y respeto de capas"
    sev: high
    depends_on: []
    acceptance: [AC6, AC8]
  - id: T29.7
    title: "Extraer cadenas del builder (platform) al catálogo español"
    sev: high
    depends_on: [T29.6]
    acceptance: [AC6]
  - id: T29.8
    title: "Extraer cadenas de AlejandrIA Magazine (projects) al catálogo español"
    sev: high
    depends_on: [T29.6]
    acceptance: [AC6]
  - id: T29.9
    title: "Catálogos en inglés del builder y de AlejandrIA Magazine con glosario"
    sev: high
    depends_on: [T29.7, T29.8]
    acceptance: [AC6]
  - id: T29.10
    title: "Selector de idioma accesible, detección inicial, lang del documento y formatos con Intl"
    sev: medium
    depends_on: [T29.6]
    acceptance: [AC1, AC6, AC12]
  - id: T29.11
    title: "Preferencias de idioma y tema por usuario: migración, endpoint PATCH y sincronización con respaldo local"
    sev: medium
    depends_on: [T29.1, T29.10]
    acceptance: [AC9]
  - id: T29.12
    title: "Códigos de error estables en la API y traducción de errores en el cliente"
    sev: medium
    depends_on: [T29.6]
    acceptance: [AC10]
  - id: T29.13
    title: "Controles de CI: paridad de claves es/en y bloqueo de literales nuevos en JSX"
    sev: medium
    depends_on: [T29.6]
    acceptance: [AC7, AC11]
  - id: T29.14
    title: "Revista pública con tema e idioma y verificación de ambos builds"
    sev: medium
    depends_on: [T29.2, T29.9, T29.10]
    acceptance: [AC3, AC6]
  - id: T29.15
    title: "Documentación de tema e i18n y recorrido manual 2 temas por 2 idiomas"
    sev: low
    depends_on: [T29.9, T29.4]
    acceptance: [AC3, AC6]
```
