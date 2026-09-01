// API calls grouped by feature. Every "auth: true" call attaches the JWT.
import { request, requestForm } from "./api.js";

export const authApi = {
  signup: (payload) => request("/api/auth/signup", { method: "POST", body: payload }),
  login: (payload) => request("/api/auth/login", { method: "POST", body: payload }),
  me: () => request("/api/auth/me", { auth: true }),
  logout: () => request("/api/auth/logout", { method: "POST", auth: true }),
};

export const departmentsApi = {
  list: () => request("/api/departments"),
};

export const adminApi = {
  listUsers: (statusFilter) =>
    request(`/api/admin/users${statusFilter ? `?status=${statusFilter}` : ""}`, {
      auth: true,
    }),
  updateUser: (userId, changes) =>
    request(`/api/admin/users/${userId}`, { method: "PATCH", body: changes, auth: true }),
};

export const documentsApi = {
  list: (view = "mine") => request(`/api/documents?view=${view}`, { auth: true }),
  uploadFile: (formData) => requestForm("/api/documents", formData),
  uploadText: (payload) =>
    request("/api/documents/text", { method: "POST", body: payload, auth: true }),
  updateVisibility: (documentId, visibility) =>
    request(`/api/documents/${documentId}/visibility`, {
      method: "PATCH",
      body: { visibility },
      auth: true,
    }),
  delete: (documentId) =>
    request(`/api/documents/${documentId}`, { method: "DELETE", auth: true }),
};

export const ragApi = {
  query: (question, conversationId = null) =>
    request("/api/rag/query", {
      method: "POST",
      body: { question, conversation_id: conversationId },
      auth: true,
    }),
  history: () => request("/api/rag/history", { auth: true }),
  status: () => request("/api/rag/status", { auth: true }),
};

export const conversationsApi = {
  list: () => request("/api/conversations", { auth: true }),
  create: (title = null) =>
    request("/api/conversations", { method: "POST", body: { title }, auth: true }),
  messages: (conversationId) =>
    request(`/api/conversations/${conversationId}/messages`, { auth: true }),
  delete: (conversationId) =>
    request(`/api/conversations/${conversationId}`, { method: "DELETE", auth: true }),
};

export const ideApi = {
  status: () => request("/api/ide/status", { auth: true }),
  startWorkspace: () => request("/api/ide/workspaces", { method: "POST", auth: true }),
  launchWorkspace: () => request("/api/ide/workspaces/launch", { method: "POST", auth: true }),
  code: () => request("/api/ide/code", { auth: true }),
  saveCode: (payload) => request("/api/ide/code", { method: "PUT", body: payload, auth: true }),
};
