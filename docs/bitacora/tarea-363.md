# Tarea #363 — T17.6: Pestaña de integridad que declara su alcance y sus límites

## 2026-11-05 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-029 · Épica E17 · AC6

### Qué se hizo y dónde

`frontend/src/projects/alejandria-magazine/pages/TraceabilityPage.jsx` — cuarta
pestaña, **Integridad**. Verifica la cadena del artículo y enseña, por ejecución:
íntegra o rota, cuántos pasos se verificaron, cuántos van sin cadena, y la lista de
problemas con su posición y su agente.

Desde ahí se exporta el JSONL (T17.4), que es donde tiene sentido: quien está
mirando si puede fiarse de la traza es quien querrá llevársela para comprobarla por
su cuenta.

### El alcance viene del servidor, no del frontend

AC6 pide decir qué garantiza la cadena **y qué no**, en la interfaz y no solo en la
documentación. Los dos textos —`guarantees` y `does_not_guarantee`— viajan en la
respuesta de `/integrity` y la pestaña los pinta desde ahí.

No están escritos en el JSX a propósito: si viviesen en el cliente, cambiar lo que
la cadena hace en el servidor dejaría la promesa vieja en pantalla, y una promesa
desactualizada sobre integridad es peor que no tener pestaña.

Lo que se declara:

- **Garantiza** — detecta que un paso se haya modificado, borrado o insertado
  después de escribirse, y dice cuál y en qué posición.
- **No garantiza** — no protege frente a quien pueda reescribir la base entera:
  con acceso de escritura se recalculan los hashes y se presenta una cadena
  coherente. No hay notarización externa ni firma; la cadena vive en la misma base
  que los datos que sella.

### Tres estados, no dos

- **Sin verificar** — todavía no se ha pulsado. No se afirma nada.
- **Sin traza** — el artículo no tiene pasos: puede no haberse ejecutado nunca o
  haberse purgado por retención. Son cosas distintas y se dicen.
- **Verificada** — íntegra o rota, con el detalle.

Si la verificación **falla** (error de red o del servidor) se dice explícitamente
que no se pudo comprobar, con esta frase: *«que no se haya podido comprobar no
significa que la traza esté bien ni que esté mal: significa que no se sabe»*. Ese
error no es mejor-esfuerzo: tragárselo y enseñar «sin problemas» sería exactamente
la confianza infundada que esta tarea existe para evitar.

Los pasos sin hash (anteriores a T17.2) se enseñan como tales, con la coletilla de
que no son señal de manipulación.

### Definition of Done

- [x] AC6: la interfaz dice qué garantiza la cadena y qué no.
- [x] Los textos vienen del servidor: no pueden divergir de lo que hace.
- [x] «No verificado», «sin traza» y «no se pudo verificar» se distinguen.
- [x] `npm run build` y el lint de estados async, en verde.
