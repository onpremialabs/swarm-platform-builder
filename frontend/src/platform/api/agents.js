import api from './client';

const BASE_API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const agentsApi = {
  // Run pipeline
  run: (articleId, data) =>
    api.post(`/api/v1/agents/${articleId}/run`, data).then(r => r.data),

  // Resume a failed pipeline from its last checkpoint (keeps completed agents' work)
  resume: (articleId, data) =>
    api.post(`/api/v1/agents/${articleId}/run`, data, { params: { resume: true } }).then(r => r.data),

  // Cancel an in-progress pipeline run
  cancel: (articleId) =>
    api.delete(`/api/v1/agents/${articleId}/run`).then(r => r.data),

  // Resolve a paused human-in-the-loop decision ("add_source" | "continue")
  submitDecision: (articleId, decision) =>
    api.post(`/api/v1/agents/${articleId}/decision`, { decision }).then(r => r.data),

  // Get run history
  getRuns: (articleId) =>
    api.get(`/api/v1/agents/${articleId}/runs`).then(r => r.data),

  // Traza de explicabilidad: por qué salió lo que salió (SPEC-014 / T9.2).
  // `scope` es 'last' (la ejecución que produjo el texto actual) o 'all'.
  getExplain: (articleId, scope = 'last') =>
    api.get(`/api/v1/agents/${articleId}/explain`, { params: { scope } }).then(r => r.data),

  // Verificación de la cadena de integridad (SPEC-029 / T17.3). La respuesta
  // trae `scope`, que dice qué garantiza la cadena **y qué no**: la interfaz lo
  // enseña desde ahí para que no pueda mostrar el sello sin sus límites (AC6).
  getIntegrity: (articleId) =>
    api.get(`/api/v1/agents/${articleId}/integrity`).then(r => r.data),

  // Descarga del JSONL (SPEC-029 / T17.4). Va por axios y no por navegación
  // directa: el endpoint pide Bearer y `X-Project-Id`, y un <a href> no los
  // lleva. Se descarga como blob y se guarda desde el cliente.
  downloadExport: async (articleId, scope = 'last') => {
    const r = await api.get(`/api/v1/agents/${articleId}/export.jsonl`, {
      params: { scope }, responseType: 'blob',
    });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement('a');
    a.href = url;
    a.download = `traza-${articleId}.jsonl`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  // Agent definitions
  getDefinitions: () =>
    api.get('/api/v1/agents/definitions').then(r => r.data),

  // Agent profiles (project-scoped)
  getClaudeDefs: (projectId) =>
    api.get('/api/v1/agents/claude-defs', { params: { project_id: projectId } }).then(r => r.data),

  updateClaudeDef: (agentId, content) =>
    api.put(`/api/v1/agents/claude-defs/${agentId}`, { content }).then(r => r.data),

  createClaudeDef: (payload) =>
    api.post('/api/v1/agents/claude-defs', payload).then(r => r.data),

  deleteClaudeDef: (agentId) =>
    api.delete(`/api/v1/agents/claude-defs/${agentId}`).then(r => r.data),

  // Available Ollama models
  getModels: () =>
    api.get('/api/v1/agents/models').then(r => r.data),

  // RAG documents
  getRagCollections: () =>
    api.get('/api/v1/agents/rag/collections').then(r => r.data),

  uploadRagDocument: (agentName, file, options = {}) => {
    const form = new FormData();
    form.append('file', file);
    if (options.ragCollection) {
      form.append('rag_collection', options.ragCollection);
    }
    if (options.ragChunkSize != null) {
      form.append('rag_chunk_size', String(options.ragChunkSize));
    }
    if (options.ragChunkOverlap != null) {
      form.append('rag_chunk_overlap', String(options.ragChunkOverlap));
    }
    return api.post(`/api/v1/agents/${agentName}/rag/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data);
  },

  getRagDocuments: (agentName) =>
    api.get(`/api/v1/agents/${agentName}/rag/documents`).then(r => r.data),

  deleteRagDocument: (agentName, docId) =>
    api.delete(`/api/v1/agents/${agentName}/rag/documents/${docId}`).then(r => r.data),

  // Global RAG library (not agent-scoped)
  getLibraryDocs: () =>
    api.get('/api/v1/agents/rag/library').then(r => r.data),

  // Re-derive title/authors for documents ingested before metadata extraction
  backfillMetadata: (collection) =>
    api.post('/api/v1/agents/rag/backfill-metadata', null, {
      params: collection ? { collection } : {},
    }).then(r => r.data),

  uploadLibraryDocument: (file, collection, chunkSize, chunkOverlap) => {
    const form = new FormData();
    form.append('file', file);
    if (collection) form.append('collection', collection);
    if (chunkSize != null) form.append('chunk_size', String(chunkSize));
    if (chunkOverlap != null) form.append('chunk_overlap', String(chunkOverlap));
    return api.post('/api/v1/agents/rag/library/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data);
  },

  deleteLibraryDocument: (collection, docId) =>
    api.delete(`/api/v1/agents/rag/library/${encodeURIComponent(collection)}/${docId}`).then(r => r.data),

  // Tool calling catalog
  getAvailableTools: () =>
    api.get('/api/v1/agents/tools').then(r => r.data),

  // Request a single-use ticket to authenticate the SSE stream. EventSource
  // cannot send an Authorization header, so we never put the JWT in the URL;
  // the client exchanges its Bearer token for a short-lived ticket instead.
  getStreamTicket: (articleId) =>
    api.post(`/api/v1/agents/${articleId}/stream-ticket`).then(r => r.data),

  // SSE stream URL (used directly with EventSource), authenticated by ticket.
  getStreamUrl: (articleId, ticket) =>
    `${BASE_API_URL}/api/v1/agents/${articleId}/stream?ticket=${encodeURIComponent(ticket)}`,
};

