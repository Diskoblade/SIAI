// Thin fetch wrapper around the backend REST API.
//
// TOKEN STORAGE NOTE (prototype decision):
//   The JWT is kept in localStorage and sent as an `Authorization: Bearer`
//   header. This is simple and adequate for the SIH prototype, but it is more
//   exposed to XSS than an HttpOnly, Secure cookie would be. For production,
//   move the token into an HttpOnly cookie and add CSRF protection.
//   No passwords are ever stored in the browser — only the short-lived token.

// Empty in local development: Vite proxies same-origin /api requests to the
// backend. Deployments with separate origins can provide an absolute URL.
const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "skp_access_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

// Normalize FastAPI/Pydantic error shapes into a single readable string.
function extractMessage(data, fallback) {
  if (!data) return fallback;
  const detail = data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    // Pydantic validation errors: [{loc, msg, ...}]
    return detail.map((e) => e.msg).join(", ");
  }
  return fallback;
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function request(path, { method = "GET", body, auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Cannot reach the server. Is the backend running?", 0);
  }

  if (response.status === 204) return null;

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    throw new ApiError(
      extractMessage(data, `Request failed (${response.status}).`),
      response.status
    );
  }
  return data;
}

// Multipart form upload (file). The browser sets the Content-Type + boundary,
// so we must NOT set it ourselves.
export async function requestForm(path, formData) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(`${API_URL}${path}`, { method: "POST", headers, body: formData });
  } catch {
    throw new ApiError("Cannot reach the server. Is the backend running?", 0);
  }

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    throw new ApiError(extractMessage(data, `Upload failed (${response.status}).`), response.status);
  }
  return data;
}

// Authenticated binary download that triggers a browser save.
export async function downloadFile(path, fallbackName = "download") {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_URL}${path}`, { headers });
  if (!response.ok) {
    throw new ApiError(`Download failed (${response.status}).`, response.status);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const name = match ? match[1] : fallbackName;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
