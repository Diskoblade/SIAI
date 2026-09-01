// Approval Note + ONLYOFFICE API client.
import { downloadFile, request, requestForm } from "./api.js";

export const approvalNotesApi = {
  // --- User ---
  listTypes: () => request("/api/approval-notes/types", { auth: true }),
  listNotes: () => request("/api/approval-notes", { auth: true }),
  getNote: (id) => request(`/api/approval-notes/${id}`, { auth: true }),
  createNote: (payload) =>
    request("/api/approval-notes", { method: "POST", body: payload, auth: true }),
  editorConfig: (id) => request(`/api/approval-notes/${id}/editor-config`, { auth: true }),
  forceSave: (id, documentKey) =>
    request(`/api/approval-notes/${id}/force-save`, {
      method: "POST",
      body: { document_key: documentKey },
      auth: true,
    }),
  downloadNote: (id, name) => downloadFile(`/api/approval-notes/${id}/download`, name),

  // --- Admin: letterhead ---
  getLetterhead: () => request("/api/admin/approval-notes/letterhead", { auth: true }),
  uploadLetterhead: (formData) => requestForm("/api/admin/approval-notes/letterhead", formData),
  downloadLetterhead: (name) =>
    downloadFile("/api/admin/approval-notes/letterhead/download", name),

  // --- Admin: types ---
  adminListTypes: () => request("/api/admin/approval-notes/types", { auth: true }),
  createType: (payload) =>
    request("/api/admin/approval-notes/types", { method: "POST", body: payload, auth: true }),
  updateType: (id, changes) =>
    request(`/api/admin/approval-notes/types/${id}`, { method: "PATCH", body: changes, auth: true }),

  // --- ONLYOFFICE health ---
  onlyofficeHealth: () => request("/api/integrations/onlyoffice/health", { auth: true }),
};
