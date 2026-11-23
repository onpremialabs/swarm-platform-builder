import api from '../../../platform/api/client';

export const articlesApi = {
  list: (params) => api.get('/api/v1/articles', { params }).then(r => r.data),
  get: (id) => api.get(`/api/v1/articles/${id}`).then(r => r.data),
  create: (data) => api.post('/api/v1/articles', data).then(r => r.data),
  update: (id, data) => api.put(`/api/v1/articles/${id}`, data).then(r => r.data),
  delete: (id) => api.delete(`/api/v1/articles/${id}`).then(r => r.data),
  submit: (id) => api.post(`/api/v1/articles/${id}/submit`).then(r => r.data),
  approve: (id) => api.post(`/api/v1/articles/${id}/approve`).then(r => r.data),
  // `comment` es un parámetro de consulta en el backend, no un cuerpo JSON.
  reject: (id, comment) =>
    api.post(`/api/v1/articles/${id}/reject`, null, { params: { comment } }).then(r => r.data),
  publish: (id) => api.post(`/api/v1/articles/${id}/publish`).then(r => r.data),
  // Compuerta de publicación (SPEC-032): último informe y si describe el texto actual.
  gateReport: (id) => api.get(`/api/v1/articles/${id}/gate-report`).then(r => r.data),
  reevaluateGate: (id) => api.post(`/api/v1/articles/${id}/gate-report`).then(r => r.data),
  // Aporta a mano el DOI de una referencia (índice del informe, desde 1) y reevalúa.
  setSourceDoi: (id, index, doi) =>
    api.put(`/api/v1/articles/${id}/gate-report/sources/${index}`, { doi }).then(r => r.data),
  // Mapa de citas vigente (SPEC-035): estado, extracto y documento/página de cada cita.
  citations: (id) => api.get(`/api/v1/articles/${id}/citations`).then(r => r.data),
  // Confirmación manual del autor: registra quién y cuándo, sin cambiar el veredicto automático.
  confirmCitation: (id, linkId) =>
    api.post(`/api/v1/articles/${id}/citations/${linkId}/confirm`).then(r => r.data),
  // Autor humano responsable (FW V13): sin él no se puede aprobar.
  setResponsibleAuthor: (id, userId) =>
    api.put(`/api/v1/articles/${id}/responsible-author`, { user_id: userId }).then(r => r.data),
  // reviewer_identifier can be an email address or a full name
  assignReviewer: (id, reviewerIdentifier) =>
    api.post(`/api/v1/articles/${id}/assign-reviewer`, { reviewer_identifier: reviewerIdentifier }).then(r => r.data),

  // Run the formateador agent on the current article body and save the result
  formatBody: (id) =>
    api.post(`/api/v1/articles/${id}/format-body`).then(r => r.data),

  // Fetch the printable paper-layout HTML (string) for the article
  getPaper: (id) =>
    api.get(`/api/v1/articles/${id}/paper`, { responseType: 'text' }).then(r => r.data),

  // Render the paper layout for *unsaved* edits. Persists nothing; the server
  // uses the same layout function as the published paper, so preview == PDF.
  previewPaper: (id, payload) =>
    api.post(`/api/v1/articles/${id}/preview`, payload, { responseType: 'text' }).then(r => r.data),

  // Upload a figure for the article; returns {id, ref, markdown} to paste in the body
  uploadAsset: (id, file) => {
    const form = new FormData();
    form.append('file', file);
    return api.post(`/api/v1/articles/${id}/assets`, form).then(r => r.data);
  },
};
