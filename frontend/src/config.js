// config.js
// Dynamic API and WebSocket URLs supporting local development and deployed production environments.

const rawApi = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export const API = rawApi.replace(/\/+$/, '');

export const WS_URL = import.meta.env.VITE_WS_URL || (
  API.startsWith('https://')
    ? API.replace('https://', 'wss://') + '/ws'
    : API.replace('http://', 'ws://') + '/ws'
);

export const STREAM_URL = `${API}/api/stream`;
