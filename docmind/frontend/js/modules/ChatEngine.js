import { $, createElement, EventBus } from '../utils/dom.js';
import { api } from '../api.js';
import { StreamRenderer } from './StreamRenderer.js';
import { CitationEngine } from './CitationEngine.js';

export class ChatEngine {
  constructor() {
    this.history = $('#chat-history');
    this.input = $('#chat-input');
    this.sendBtn = $('#btn-send-chat');
    this.emptyState = $('#chat-empty-state');
    
    this.messages = [];
    this.activeSourceIds = [];
    this.init();
  }

  init() {
    this.sendBtn.onclick = () => this.sendMessage();
    this.input.onkeydown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    };

    EventBus.on('sources:updated', (sources) => {
      this.activeSourceIds = sources.filter(s => s.active).map(s => s.id);
    });

    EventBus.on('chat:set-input', (text) => {
      this.input.value = text;
      this.input.focus();
    });
  }

  async sendMessage() {
    const text = this.input.value.trim();
    if (!text) return;
    
    if (this.activeSourceIds.length === 0) {
      alert('Please activate at least one source to chat.');
      return;
    }

    this.input.value = '';
    this.emptyState.style.display = 'none';

    // Add user message
    this.addMessage('user', text);
    
    // Add temporary assistant message for streaming
    const assistantMsg = this.addMessage('assistant', '');
    const bubble = $('.message-bubble', assistantMsg);
    bubble.classList.add('stream-cursor');

    let fullResponse = '';
    let citations = [];

    try {
      await api.stream('/chat', {
        message: text,
        history: this.messages.slice(0, -1),
        active_source_ids: this.activeSourceIds
      }, 
      (token) => {
        fullResponse += token;
        // Strip citations block if it starts to appear
        const cleanContent = CitationEngine.parseCitations(fullResponse, []).text;
        bubble.innerHTML = window.marked.parse(cleanContent);
      },
      (data) => {
        if (data.citations) {
          citations = data.citations;
          const { text: cleanContent } = CitationEngine.parseCitations(fullResponse, citations);
          bubble.innerHTML = window.marked.parse(cleanContent);
          CitationEngine.injectBadges(bubble, citations);
        }
        if (data.done) {
          bubble.classList.remove('stream-cursor');
          const cleanHistory = CitationEngine.parseCitations(fullResponse, citations).text;
          this.messages.push({ role: 'assistant', content: cleanHistory, citations });
        }
      });
    } catch (e) {
      console.error('Chat stream failed', e);
      bubble.innerHTML = '<p style="color: #ef4444;">Sorry, I encountered an error.</p>';
      bubble.classList.remove('stream-cursor');
    }
  }

  addMessage(role, content) {
    const bubble = createElement('div', { className: 'message-bubble' });
    
    // For assistant, we use innerHTML to render Markdown/Citations
    // For user, we treat as plain text for safety and clean UI
    if (role === 'assistant' && content) {
      bubble.innerHTML = window.marked ? window.marked.parse(content) : content;
    } else {
      bubble.textContent = content;
    }

    const msgElement = createElement('div', { className: `message message-${role}` }, [bubble]);
    
    this.history.appendChild(msgElement);
    this.history.scrollTop = this.history.scrollHeight;
    
    if (content) {
      this.messages.push({ role, content });
    }
    
    return msgElement;
  }
}
