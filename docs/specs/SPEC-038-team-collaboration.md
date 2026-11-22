# SPEC-038: Colaboración de equipo sobre un manuscrito

- **Estado:** Ready
- **Autor:** Equipo de plataforma (borrador asistido)
- **Fecha:** 2026-11-22
- **Épica:** E26 (GitHub Project)
- **ADR relacionado:** [SPEC-037](SPEC-037-authorship-declarations-and-manuscript-metadata.md) (autoría y CRediT) · [SPEC-022](SPEC-022-editable-paper-output.md) (edición; excluye tiempo real)
- **Severidad:** 🟡

> **Origen.** Análisis del 2026-11-22: un paper lo escribe un equipo, y hoy hay un
> autor y un revisor asignado. Pasa a `Ready` por instrucción del equipo;
> `/speckit-clarify` y `/speckit-checklist` pendientes (no bloqueantes).

## 1. Problema

- `ArticleDetailPage` ofrece «Asignar revisor» (una persona, por email o nombre) y
  «Declarar autor responsable». No hay coautores con contribución propia, ni
  secciones asignadas, ni comentarios por párrafo.
- Editar el cuerpo (`updateArticle`) **sobrescribe**: no hay historial de versiones
  ni comparación entre la versión del pipeline, la editada y la aprobada. SPEC-032
  exige que la aprobación humana vincule «la versión»; sin versiones navegables esa
  vinculación no es auditable por el equipo.
- Los roles existentes (admin, redactor, revisor, lector) no distinguen
  coautor/colaborador por artículo.
- SPEC-022 excluye expresamente la edición colaborativa en tiempo real; esta spec
  **no** la introduce: es colaboración asíncrona.

## 2. Objetivos / No-objetivos

- **Objetivos:** (a) coautores y colaboradores por artículo con permisos
  explícitos; (b) asignar **secciones** a personas; (c) **comentarios** por párrafo
  con hilo y resolución; (d) **versiones** del manuscrito con diferencias; (e)
  notificaciones de lo que requiere atención.
- **No-objetivos:** edición simultánea tipo documento compartido; resolución
  automática de conflictos de texto; chat general; sustituir al control de
  versiones de código del equipo.

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* un artículo *When* la persona propietaria invita a otra
  como `coautor`, `colaborador` o `lector` *Then* se registra el rol y la persona
  solo puede hacer lo que su rol permite (verificado por tests de autorización, sin
  escalada de privilegios).
- [ ] **AC2** — *Given* un manuscrito con secciones IMRaD *When* se asigna una
  sección a una persona *Then* la asignación es visible y las ediciones en esa
  sección quedan atribuidas a quien las hace.
- [ ] **AC3** — *Given* un párrafo *When* una persona comenta *Then* el comentario
  se ancla al párrafo (por identificador estable), admite respuestas y puede
  marcarse como resuelto por una persona autorizada.
- [ ] **AC4** — *Given* un cambio en el cuerpo *When* se guarda *Then* se crea una
  **versión inmutable** con autor, fecha, origen (pipeline o edición manual) y hash,
  y existe una vista de diferencias entre dos versiones.
- [ ] **AC5** — *Given* la aprobación humana *When* se registra *Then* referencia la
  versión concreta aprobada y la UI avisa si el texto cambió después.
- [ ] **AC6** — *Given* un comentario nuevo o una asignación *When* ocurre *Then*
  las personas afectadas reciben notificación (centro existente de
  notificaciones).
- [ ] **AC7** — *Given* los comentarios *When* un comentarista escribe texto
  *Then* se sanea en el cliente y en el servidor (sin HTML ejecutable) y respeta el
  aislamiento por proyecto.

## 4. Diseño propuesto

- **Datos (Alembic):** `article_members` (rol), `article_versions`
  (contenido, hash, origen, autor), `article_comments` (ancla, hilo, estado) y
  `section_assignments`.
- **Anclas:** los párrafos reciben identificador estable al renderizar el
  Markdown para sobrevivir a ediciones menores; si el ancla desaparece, el
  comentario pasa a «huérfano» y se conserva.
- **API:** rutas bajo `routers/articles.py` con `get_project_context` y el
  chequeo de rol por artículo; reutilizar `notifications.py`.
- **Frontend:** panel lateral de comentarios, selector de versiones y diff en el
  detalle del artículo.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Autorización incompleta expone borradores | Alto | Tests por rol y por proyecto; denegar por defecto |
| Crecimiento de `article_versions` | Medio | Retención configurable y compactación de versiones intermedias del pipeline |
| Anclas frágiles ante reescrituras del pipeline | Medio | Estado «huérfano» visible; reanclado manual |
| XSS en comentarios | Alto | Saneamiento y CSP existentes (SPEC-016); test de inyección |

## 6. Plan de pruebas

Matriz de autorización por rol y proyecto; pruebas de versionado e integridad del
hash; prueba del diff con casos de reescritura; prueba de saneamiento; manual: dos
usuarios comentando y resolviendo.

## 7. Impacto operativo / observabilidad

Migraciones aditivas; actualizar `data-retention.md` (versiones y comentarios son
rastro acumulado). Métricas: comentarios abiertos, versiones por artículo.
Despliegue tras flag `TEAM_COLLAB_ENABLED`.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E26
  title: "Colaboración de equipo sobre un manuscrito"
  area: area/backend
tasks:
  - id: T26.1
    title: "Migración y modelos: article_members, article_versions, article_comments y section_assignments"
    sev: high
    depends_on: []
    acceptance: [AC1, AC4]
  - id: T26.2
    title: "Roles por artículo y autorización con tests de denegación por defecto"
    sev: high
    depends_on: [T26.1]
    acceptance: [AC1, AC7]
  - id: T26.3
    title: "Versionado inmutable del manuscrito con hash y origen"
    sev: high
    depends_on: [T26.1]
    acceptance: [AC4, AC5]
  - id: T26.4
    title: "API de comentarios anclados con hilos, resolución y saneamiento"
    sev: medium
    depends_on: [T26.2]
    acceptance: [AC3, AC7]
  - id: T26.5
    title: "Asignación de secciones y atribución de ediciones"
    sev: medium
    depends_on: [T26.2, T26.3]
    acceptance: [AC2]
  - id: T26.6
    title: "Frontend: comentarios por párrafo, selector de versiones y diff"
    sev: medium
    depends_on: [T26.3, T26.4]
    acceptance: [AC3, AC4]
  - id: T26.7
    title: "Notificaciones de comentarios y asignaciones"
    sev: low
    depends_on: [T26.4, T26.5]
    acceptance: [AC6]
```
