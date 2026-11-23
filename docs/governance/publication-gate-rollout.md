# Despliegue gradual de la compuerta de publicación

SPEC-032 / ADR-0011 · DEC-4. La compuerta **falla cerrada**: con `PUBLICATION_GATE_ENFORCE=true`, lo que no se puede comprobar bloquea. Hoy casi
ningún borrador pasaría, porque las fuentes del RAG no traen DOI. Por eso se despliega en **modo aviso** y se activa cuando los bloqueantes
sean accionables.

## Qué cambia según el modo

| | `gate_enforce: false` (modo aviso, **estado actual**) | `gate_enforce: true` (por defecto del código) |
|---|---|---|
| Informe de la compuerta | Se genera y se guarda igual. | Igual. |
| `failed` / `not_verified` | Se registran y se avisan; **no impiden** llegar a aprobación. | Bloquean. |
| Aprobación humana | **Sigue siendo obligatoria**, también autor responsable y revisión (≥ 80). | Igual. |
| Quedan constancia en | La auditoría de la aprobación (`gate_warning`, `gate_warnings`). | — |

Dónde se declara: `publication.gate_enforce` en `config.yaml` (raíz y `backend/`, deben coincidir; un test lo comprueba) o la variable de entorno
`PUBLICATION_GATE_ENFORCE`. **El valor por defecto del código sigue siendo `true`**: un entorno sin configuración falla cerrado.

## Procedimiento

1. **Desplegar en modo aviso** (ya es así en `config.yaml`). Trabajo normal durante 1–2 semanas; quien revisa ve el informe, aporta DOI a mano y reejecuta.
2. **Medir** cada semana, contra la base del entorno:
   ```bash
   cd backend && DATABASE_URL=… python ../scripts/gate_rollout_report.py --days 14
   ```
   Da cuántos manuscritos (último informe de cada uno) pasarían, cuántos se bloquean por **un solo criterio** (corrección acotada) y qué criterios bloquean más.
   Recomienda activar solo con **al menos 20 manuscritos** y **≥ 80 %** que pasarían (ajustables con `--min-articles` y `--min-pass`).
3. **Atacar lo que más bloquea** antes de activar. Lo habitual: referencias sin DOI (se aporta a mano desde el panel, o llegan con identificador cuando
   la búsqueda externa de la Fase 4 esté hecha) y estructura IMRaD (se reejecuta desde el Redactor).
4. **Activar** (`gate_enforce: true` en las dos copias de `config.yaml`, en una PR con su bitácora). **Lo decide una persona**: el script solo recomienda.
5. **Vigilar** las primeras semanas: métricas `publication_gate_criterion_total`, `publication_gate_reference_total` y `publication_gate_external_errors_total`.
   Un pico de `external_errors` (Crossref/OpenAlex/DataCite) indica un problema del servicio, no de los manuscritos.

## Volver atrás

Si al activar la compuerta bloquea trabajo correcto por una caída externa o un criterio demasiado estricto, vuelve a `gate_enforce: false` (misma PR de dos
líneas). No hay migración ni datos que deshacer: los informes ya guardados siguen valiendo.

## Soporte de citas (`citation_support`, SPEC-035 / T23.8)

Se despliega aparte y **en modo aviso**: `CITATION_SUPPORT_ENFORCE` (por defecto `false`; `publication.citation_support_enforce` en `config.yaml`) hace que el criterio
aparezca en el informe con su estado real (`not_verified` y el motivo: `no_citations`, `map_unavailable`, `no_fragment`, `low_overlap`...) y la marca `advisory`, pero sin bloquear.
Con `true` bloquea como el resto de criterios. El Publicador guarda el mapa cita→fragmento sobre el texto final antes de evaluar. Pasar a `true` es una decisión posterior,
con datos de falsos positivos (`low_overlap` es una heurística de solape, no un juicio). Solo actúa si la plantilla declara `gate.citation_support`.
