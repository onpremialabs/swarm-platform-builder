# ADR-0013: Fuentes aportadas por el autor y verificación de identificadores diferida a la compuerta

- **Estado:** Propuesto
- **Fecha:** 2026-11-23
- **Decisores:** Equipo de plataforma (la decisión de producto la pide el mantenedor; ver *Origen*)
- **Specs relacionadas:** [SPEC-032](../specs/SPEC-032-publication-gate-framework.md) · [SPEC-034](../specs/SPEC-034-verified-literature-discovery-and-library.md) · [SPEC-035](../specs/SPEC-035-citation-support-and-retractions.md)
- **Enmienda parcialmente:** [ADR-0011](0011-publication-gate-fail-closed.md) (decisiones 3 y 5 y la alternativa «excepción para documentos aportados por el autor»)
- **Origen:** prueba manual del 2026-11-23. El Investigador se abstuvo con 0/3 fuentes verificadas
  teniendo documentos relevantes subidos por la persona, y no produjo nada. El mantenedor pidió que
  el Investigador pueda **generar ágilmente un paper a partir de los borradores y PDFs que la
  persona aporta**, que el DOI se compruebe **después** de generar y formatear el contenido, y
  que quien lanzó el pipeline pueda publicar su propio artículo.

## Contexto

ADR-0011 decidió que cada referencia se resuelve contra Crossref/OpenAlex/DataCite por DOI o por
título y autores, «sin excepción para documento interno», y descartó expresamente la alternativa
de una excepción para documentos aportados por el autor: reabre «exactamente la puerta que cierra
V09». SPEC-034 lo trasladó al Investigador (T22.5): solo cita documentos con DOI verificado y se
abstiene con menos de `research.min_sources` (3). La aclaración de SPEC-034 del 2026-11-22
(pregunta 1, opción A) lo confirmó. ADR-0011 decidió además (5) que aprueba **una persona
distinta** de quien lanzó el pipeline.

El efecto observado es que el flujo se detiene antes de empezar a escribir para todo documento sin
identificador resoluble: borradores propios, informes, tesis, material no publicado. Para estos
documentos, además, el DOI no es lo que evita la cita inventada: el documento **existe** porque la
persona lo subió, y que la cita lo respalde se comprueba contra su fragmento (SPEC-035). El DOI
aporta localizabilidad para el lector y la comprobación de retractaciones (Crossref), que sí
necesitan un identificador.

Esta enmienda **cambia una decisión que se había descartado de forma explícita**. Se registra
aquí como tal, con sus costes, y no como un ajuste de implementación.

## Decisión

1. **Dos clases de fuente citable** en la biblioteca del proyecto:
   - **Identificada:** con DOI verificado (resuelto por el sistema o aportado por el autor y
     verificado). Es el comportamiento actual.
   - **Aportada por el autor:** sin identificador resoluble, **declarada como tal por una persona**,
     con registro de quién y cuándo. Nunca la asigna el sistema ni el modelo.
2. **Un DOI declarado que no resuelve o no coincide sigue siendo un defecto bloqueante.** No se
   rebaja a «aportada por el autor»: así un identificador inventado no se «lava». Solo el
   documento **sin identificador declarado** puede entrar como clase 2.
3. **La verificación de identificadores no frena la generación.** El Investigador puede usar y
   citar cualquier documento **aceptado** de la biblioteca, de las dos clases, con las etiquetas
   que corresponda. `research.min_sources` pasa a contar **fuentes citables** (identificadas o
   aportadas por el autor) con texto utilizable (`full_text` o `abstract_only`), y se mantiene el
   mínimo: el Investigador sigue **sin sintetizar desde el conocimiento paramétrico** y se abstiene
   si no hay fuentes suficientes. Se abstiene por falta de **fuentes**, no por falta de DOI.
4. **El DOI se comprueba en la compuerta**, sobre el texto final tras el Formateador, como ya
   prevé ADR-0011 (decisión 1). V09 trata cada clase así:
   - Identificada: igual que hoy (existencia y coincidencia; discrepancia bloquea; no resuelta,
     `not_verified` y bloquea).
   - Aportada por el autor: no se resuelve en servicios externos. Su estado en el informe es
     `author_supplied` y su severidad la fija `gate.references.author_supplied: block | warn` en
     `template.yaml`. **Por defecto `block`**, de modo que ningún proyecto cambia de
     comportamiento sin declararlo; AlejandrIA declara `warn`.
   - Con `warn`: no bloquea, el informe las lista una a una, Referencias las etiqueta
     («documento aportado por el autor, sin identificador») y el informe dice que **no se pudo
     comprobar su retractación**. La estructura mínima exigida a esta clase sustituye al
     identificador por: autores, año, título o nombre del documento y tipo de documento.
   - El soporte de **cada cita** frente a su fragmento (SPEC-035) se comprueba igual en las dos
     clases.
5. **Aprobación por la misma persona, por proyecto.** La decisión 5 de ADR-0011 pasa a ser el
   **valor por defecto**. Un proyecto puede declarar `approval.allow_self_approval: true` en
   `template.yaml` (validado al cargar; no lo cambia el autor por artículo). Con ella, quien lanzó
   el pipeline puede aprobar y publicar su artículo. **No se omite nada más:** el Revisor, la
   compuerta, `requires_human_review` y la huella del texto aprobado se aplican igual. El registro
   de aprobación guarda `self_approved=true` y el informe de compuerta lo dice («sin revisión
   independiente»). El interruptor global `PUBLICATION_ALLOW_SELF_APPROVAL` (solo con `DEBUG`) se
   mantiene para desarrollo y no cambia.

## Alternativas consideradas

- **Mantener ADR-0011 y mejorar solo el flujo** (botón «Buscar literatura» en el aviso de
  abstención, SPEC-034). Ayuda a conseguir fuentes con DOI, pero no resuelve el caso de los
  propios borradores y PDFs sin identificador. Se conserva como mejora complementaria.
- **Excepción general para «documento interno» sin etiqueta ni severidad.** La que ADR-0011
  descartó. Sigue descartada: aquí la clase es **explícita, declarada por una persona, visible en
  Referencias y configurable en severidad**.
- **Verificar el DOI en el Investigador pero degradar a aviso.** Mantiene la abstención por
  documentos sin DOI y conserva el mismo punto de fricción antes de generar. Rechazada.
- **Hacer pasar al documento sin identificador por una resolución «por título» laxa.** Reduciría
  el umbral de coincidencia de V09 para acomodar casos que no existen en esos servicios. Rechazada:
  ADR-0011 y su enmienda de DataCite dejan claro que el umbral no se relaja.
- **Un LLM que juzgue si el documento «parece real».** El fallo que el framework documenta; la
  comprobación debe ser determinista. Descartada.
- **Autoaprobación global sin interruptor por proyecto.** Cambia el valor por defecto de todas las
  instalaciones. Rechazada.

## Consecuencias

- **Positivas:** el Investigador puede generar un paper a partir de lo que la persona aporta sin
  pasar antes por la resolución de DOI; la verificación externa sigue ocurriendo, pero al final,
  sobre el texto formateado; un proyecto que no declare nada se comporta como hoy; quien trabaja
  solo puede publicar su artículo.
- **Negativas / coste:**
  - **Menos verificabilidad externa.** Una revista con muchas fuentes sin identificador pierde que
    el lector las localice y que se compruebe su retractación. Queda etiquetado, pero no resuelto.
  - **Se elimina el principio de dos personas** donde se active la autoaprobación. Lo compensan la
    compuerta determinista, el soporte de cada cita y el registro `self_approved`, pero no es
    equivalente a una revisión independiente.
  - **Riesgo de abuso:** declarar «aportada por el autor» una fuente que en realidad es dudosa.
    Mitigación: la fuente debe ser un documento presente en la biblioteca (no una cadena libre),
    la declaración queda registrada y visible, el DOI declarado erróneo sigue bloqueando y el
    informe la lista.
  - Cambia comportamiento ya implementado y probado: T22.5, T22.9 (datasets EDD que afirman «un
    documento interno sin verificar no se cita»), AC4/AC5/AC7 de SPEC-034, V09 y AC8 de SPEC-032.
- **Seguimiento:** specs afectadas y tareas nuevas (ver las specs). Medir la proporción de
  referencias `author_supplied` en artículos publicados y su relación con los bloqueos del soporte
  de citas. Si el panel de validación o esa medición lo desaconsejan, se reemplaza este ADR.
