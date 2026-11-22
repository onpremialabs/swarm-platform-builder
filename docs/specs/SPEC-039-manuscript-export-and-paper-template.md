# SPEC-039: Exportación del manuscrito y plantilla «Paper científico»

- **Estado:** Ready
- **Autor:** Equipo de plataforma (borrador asistido)
- **Fecha:** 2026-11-22
- **Épica:** E27 (GitHub Project)
- **ADR relacionado:** [SPEC-022](SPEC-022-editable-paper-output.md) (maquetación HTML) · [SPEC-013](SPEC-013-structural-refactor-project-independence.md) (plantillas de proyecto) · [SPEC-033](SPEC-033-paper-brief-and-author-data.md) (brief)
- **Severidad:** 🟡

> **Origen.** Análisis del 2026-11-22; PaperOrchestra entrega LaTeX y PDF con la
> plantilla del congreso. Pasa a `Ready` por instrucción del equipo;
> `/speckit-clarify` y `/speckit-checklist` pendientes (no bloqueantes).

## 1. Problema

- La salida es una **maquetación HTML imprimible** (`adapters/paper_layout.py`,
  `GET /articles/{id}/paper`) con una plantilla por estilo de cita. Una revista o un
  congreso piden LaTeX o .docx con su plantilla y un `.bib`; hoy el equipo tiene
  que rehacer el manuscrito a mano.
- Las referencias existen solo dentro del texto formateado; no hay exportación
  BibTeX/CSL.
- El **Flow Designer abre vacío** («Diseña tu pipeline»): una persona
  investigadora no parte de un proyecto pensado para papers. AlejandrIA Magazine
  es una *revista*; no hay plantilla de proyecto «Paper científico» con su brief,
  guías de reporte y pasos propios (SPEC-013/T8.4 hace posible crearla sin tocar
  Python).

## 2. Objetivos / No-objetivos

- **Objetivos:** (a) exportar el manuscrito a **LaTeX** y **.docx** con plantillas
  por revista/congreso; (b) exportar **BibTeX/CSL JSON** de las referencias
  verificadas; (c) paquete descargable reproducible; (d) **plantilla de proyecto
  «Paper científico»** y flujo precargado en el Flow Designer.
- **No-objetivos:** compilar LaTeX en el servidor; plantillas de todas las
  revistas (se empieza por un conjunto pequeño extensible); enviar el manuscrito a
  plataformas de revistas; figuras generadas (queda fuera).

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* un artículo aprobado *When* se pide exportar a LaTeX
  *Then* se descarga un `.zip` con `main.tex`, la plantilla elegida y `references.bib`
  que **solo contiene referencias de la biblioteca verificada**.
- [ ] **AC2** — *Given* el mismo artículo *When* se exporta a .docx *Then* conserva
  estructura IMRaD, citas y lista de referencias según el estilo elegido.
- [ ] **AC3** — *Given* una exportación *When* se repite con la misma versión
  *Then* el contenido es idéntico (determinista) y el paquete incluye el hash de la
  versión exportada.
- [ ] **AC4** — *Given* un artículo sin aprobación humana o con la compuerta
  bloqueante *When* se intenta exportar un paquete «final» *Then* se rechaza; solo
  se permite un borrador marcado como tal.
- [ ] **AC5** — *Given* contenido con caracteres especiales de LaTeX *When* se
  exporta *Then* se escapa correctamente y no es posible inyectar comandos
  (verificado con casos de prueba).
- [ ] **AC6** — *Given* el catálogo de plantillas como dato del proyecto *When* se
  añade una plantilla nueva *Then* basta con registrarla en `template.yaml` y se
  valida al cargar, sin tocar Python.
- [ ] **AC7** — *Given* un proyecto nuevo *When* se crea desde «Paper científico»
  *Then* trae agentes, brief, guías de reporte y un flujo precargado en el Flow
  Designer.

## 4. Diseño propuesto

- **Exportadores** en `backend/app/modules/agents/adapters/` (o módulo propio
  `platform/export/`), uno por formato, con interfaz común.
- **Plantillas** versionadas en `backend/projects/<slug>/export/`, referenciadas
  desde `template.yaml`.
- **Escape y sandbox:** sin ejecución de código; el LaTeX no se compila en el
  servidor.
- **Proyecto nuevo:** `backend/projects/paper-cientifico/template.yaml` con sus
  perfiles `.agent.md`, validado por `platform/projects/`.
- **Frontend:** menú «Exportar» en el detalle del artículo y selector de plantilla
  en el modal del Flow Designer.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Inyección de comandos LaTeX | Alto | Escape estricto y lista de entornos permitidos; tests dedicados |
| Licencias de plantillas de congreso | Medio | Incluir solo plantillas con licencia compatible; si no, enlazar a la oficial |
| Fidelidad .docx limitada | Medio | Documentar límites; empezar por estilos básicos |
| Exportar borradores como si fueran finales | Alto | Marca de agua «borrador» y AC4 |

## 6. Plan de pruebas

Pruebas de escape con corpus adversarial; prueba de determinismo; prueba del
contenido del `.bib` frente a la biblioteca; apertura del `.docx` en un lector
estándar; manual: crear proyecto desde la plantilla y recorrerlo.

## 7. Impacto operativo / observabilidad

Sin migración de datos. Métrica: exportaciones por formato. Los paquetes se generan
bajo demanda y no se almacenan (sin nueva retención). Flag
`MANUSCRIPT_EXPORT_ENABLED`.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E27
  title: "Exportación del manuscrito y plantilla Paper científico"
  area: area/backend
tasks:
  - id: T27.1
    title: "Exportador LaTeX con paquete reproducible y escape estricto"
    sev: high
    depends_on: []
    acceptance: [AC1, AC3, AC5]
  - id: T27.2
    title: "Exportación BibTeX y CSL JSON de la biblioteca verificada"
    sev: medium
    depends_on: []
    acceptance: [AC1]
  - id: T27.3
    title: "Exportador .docx con estructura IMRaD y estilo de citas"
    sev: medium
    depends_on: []
    acceptance: [AC2, AC3]
  - id: T27.4
    title: "Catálogo de plantillas de revista/congreso como dato de template.yaml con validación"
    sev: medium
    depends_on: [T27.1]
    acceptance: [AC6]
  - id: T27.5
    title: "Regla: solo borradores sin aprobación y marca de agua"
    sev: high
    depends_on: [T27.1]
    acceptance: [AC4]
  - id: T27.6
    title: "Proyecto Paper científico con agentes, guías y flujo precargado en el Flow Designer"
    sev: medium
    depends_on: []
    acceptance: [AC7]
  - id: T27.7
    title: "Frontend: menú Exportar y selector de plantilla"
    sev: low
    depends_on: [T27.1, T27.3]
    acceptance: [AC1, AC2]
```
