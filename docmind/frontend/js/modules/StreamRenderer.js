import { $ } from '../utils/dom.js';

export class StreamRenderer {
  constructor(containerId) {
    this.container = $(containerId);
    this.fullText = '';
  }

  clear() {
    this.fullText = '';
    this.container.innerHTML = '';
    this.container.classList.add('stream-cursor');
  }

  appendToken(token) {
    this.fullText += token;
    // Using marked.js which is loaded via CDN in index.html
    if (window.marked) {
      this.container.innerHTML = window.marked.parse(this.fullText);
    } else {
      this.container.innerText = this.fullText;
    }
    
    // Auto-scroll to bottom of the pane content if it's chat
    const paneContent = this.container.closest('.pane-content');
    if (paneContent) {
      paneContent.scrollTop = paneContent.scrollHeight;
    }
  }

  done() {
    this.container.classList.remove('stream-cursor');
  }
}
