import axios from 'axios';

const rawEnvUrl = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
let cleanBase = rawEnvUrl.trim().replace(/\/+$/, '');
// Ensure it ends with /api cleanly without duplicating (e.g. avoiding /api/api)
if (!cleanBase.endsWith('/api')) {
  cleanBase = `${cleanBase}/api`;
}
const API_BASE_URL = cleanBase;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * POST JSON and read a server-sent event stream.
 * Calls onStep(event) for each `step`, resolves with the `result` payload,
 * rejects with an Error carrying the server's message on `error` or HTTP failure.
 */
export async function streamPost(path, body, onStep) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Request failed (HTTP ${res.status})`;
    try {
      const j = await res.json();
      if (typeof j.detail === 'string') detail = j.detail;
      else if (Array.isArray(j.detail)) detail = j.detail.map((d) => d.msg).join('; ');
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const event = /^event: (.*)$/m.exec(chunk)?.[1];
      const data = /^data: (.*)$/m.exec(chunk)?.[1];
      if (!event || data === undefined) continue;
      const payload = JSON.parse(data);
      if (event === 'step') onStep?.(payload);
      else if (event === 'result') result = payload;
      else if (event === 'error') throw new Error(payload.detail || 'Server error');
    }
  }
  if (!result) throw new Error('The server closed the stream without a result.');
  return result;
}

export const runBrief = ({ firText, perspective }, onStep) =>
  streamPost('/brief', { fir_text: firText, perspective }, onStep);

export const runAudit = ({ draftText }, onStep) =>
  streamPost('/audit', { draft_text: draftText }, onStep);

export const getSamples = async () => (await apiClient.get('/samples')).data;

export const uploadPDF = async (file) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiClient.post('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const checkHealth = async () => {
  const response = await apiClient.get('/health');
  return response.data;
};
