import { $, createElement, EventBus } from '../utils/dom.js';
import { api } from '../api.js';
import { StreamRenderer } from './StreamRenderer.js';

export class SourceViewer {
  constructor() {
    this.summaryText = $('#summary-text');
    this.questionsGrid = $('#questions-grid');
    this.renderer = new StreamRenderer('#summary-text');
    
    this.activeSourceIds = [];
    this.init();
  }

  init() {
    EventBus.on('sources:updated', (sources) => {
      this.activeSourceIds = sources.filter(s => s.active).map(s => s.id);
      this.refreshSummary();
      this.refreshQuestions();
    });
  }

  async refreshSummary() {
    if (this.activeSourceIds.length === 0) {
      this.summaryText.innerHTML = '<p style="color: var(--clr-text-muted); font-style: italic;">Select sources to generate a summary.</p>';
      return;
    }

    this.renderer.clear();
    try {
      await api.stream('/summary', { source_ids: this.activeSourceIds }, 
        (token) => this.renderer.appendToken(token),
        (done) => this.renderer.done()
      );
    } catch (e) {
      console.error('Summary stream failed', e);
      this.summaryText.innerHTML = '<p style="color: #ef4444;">Failed to generate summary.</p>';
    }
  }

  async refreshQuestions() {
    if (this.activeSourceIds.length === 0) {
      this.questionsGrid.innerHTML = '';
      return;
    }

    try {
      const { questions } = await api.get(`/suggested-questions?source_ids=${this.activeSourceIds.join(',')}`);
      this.renderQuestions(questions);
    } catch (e) {
      console.error('Failed to fetch questions', e);
    }
  }

  renderQuestions(questions) {
    this.questionsGrid.innerHTML = '';
    questions.forEach(q => {
      const chip = createElement('div', {
        className: 'question-chip',
        onclick: () => EventBus.emit('chat:set-input', q)
      }, q);
      this.questionsGrid.appendChild(chip);
    });
  }
}
