/**
 * API Client - Fetch + SSE abstraction layer
 */

const BASE_URL = 'http://localhost:8000';

export const api = {
  async get(path) {
    const res = await fetch(`${BASE_URL}${path}`);
    if (!res.ok) throw new Error(`API Error: ${res.statusText}`);
    return res.json();
  },

  async post(path, body) {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error(`API Error: ${res.statusText}`);
    return res.json();
  },

  async patch(path, body) {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error(`API Error: ${res.statusText}`);
    return res.json();
  },

  async delete(path) {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error(`API Error: ${res.statusText}`);
    return res.json();
  },

  /**
   * SSE Stream Handler
   * @param {string} path 
   * @param {object} body 
   * @param {function} onToken 
   * @param {function} onMetadata 
   */
  async stream(path, body, onToken, onMetadata) {
    const response = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    if (!response.ok) throw new Error(`Stream Error: ${response.statusText}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6));
            if (data.token) onToken(data.token);
            if (data.citations || data.done) onMetadata(data);
          } catch (e) {
            console.error('Error parsing SSE data', e);
          }
        }
      }
    }
  }
};
