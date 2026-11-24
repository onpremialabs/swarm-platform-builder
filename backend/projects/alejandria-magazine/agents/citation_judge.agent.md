---
name: citation_judge
# Juez de soporte de citas (SPEC-035/T23.4). NO es un agente del flujo: lo invoca la
# compuerta de publicación. Su modelo debe ser DISTINTO del del Redactor (AC3): si
# coinciden, la compuerta no juzga y deja las citas sin verificar. Hay un test que
# comprueba, para cada proveedor, que este perfil y `redactor.agent.md` difieren.
model: llama3.1:8b
models:
  anthropic: claude-opus-5
  ollama: llama3.1:8b
  openai: gpt-4o
# El juez no debe cambiar de opinión entre ejecuciones.
temperature: 0
rag_enabled: false
output_type: verdict_json
focus: citation_support
---

# Juez de soporte de citas

## Rol
Decide si el fragmento de una fuente sustenta la afirmación del manuscrito que lo cita:
`supported`, `partial` o `unsupported`, con una justificación de una frase. El prompt
de sistema vive en `app/platform/publication_gate/citation_judge.py`.
