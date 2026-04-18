import { $, $$, createElement, EventBus } from '../utils/dom.js';
import { api } from '../api.js';

export class SourceManager {
  constructor() {
    this.container = $('#source-list-container');
    this.emptyState = $('#sources-empty-state');
    this.uploadTrigger = $('#btn-upload-trigger');
    this.modal = $('#upload-modal');
    this.dropZone = $('#drop-zone');
    this.fileInput = $('#file-input');
    this.btnClose = $('.btn-close', this.modal);
    
    // UI elements for URL ingestion
    this.modalTabs = $$('.modal-tab', this.modal);
    this.modalTabContents = $$('.modal-tab-content', this.modal);
    this.urlInput = $('#url-input');
    this.btnImportUrl = $('#btn-import-url');
    this.urlStatus = $('#url-status');

    this.sources = [];
    this.init();
  }

  async init() {
    this.bindEvents();
    await this.fetchSources();
  }

  bindEvents() {
    this.uploadTrigger.onclick = () => this.showModal();
    this.btnClose.onclick = () => this.hideModal();
    this.modal.onclick = (e) => {
      if (e.target === this.modal) this.hideModal();
    };

    // Tab switching
    this.modalTabs.forEach(tab => {
      tab.onclick = () => this.switchTab(tab.dataset.tab);
    });

    // Import from URL
    this.btnImportUrl.onclick = () => this.handleUrlImport();

    // Upload logic
    this.dropZone.onclick = () => this.fileInput.click();
    this.dropZone.ondragover = (e) => {
      e.preventDefault();
      this.dropZone.classList.add('dragover');
    };
    this.dropZone.ondragleave = () => this.dropZone.classList.remove('dragover');
    this.dropZone.ondrop = (e) => {
      e.preventDefault();
      this.dropZone.classList.remove('dragover');
      this.handleFiles(e.dataTransfer.files);
    };
    this.fileInput.onchange = (e) => this.handleFiles(e.target.files);
  }

  showModal() { 
    this.modal.style.display = 'flex'; 
    this.switchTab('file');
    this.urlInput.value = '';
    this.urlStatus.style.display = 'none';
  }

  hideModal() { this.modal.style.display = 'none'; }

  switchTab(tabId) {
    this.modalTabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tabId));
    this.modalTabContents.forEach(c => c.classList.toggle('active', c.id === `modal-tab-${tabId}`));
  }

  async handleUrlImport() {
    const url = this.urlInput.value.trim();
    if (!url) return;

    this.urlStatus.textContent = 'Downloading and processing...';
    this.urlStatus.style.display = 'block';
    this.btnImportUrl.disabled = true;

    try {
      const source = await api.post('/sources/url', { url });
      this.sources.push(source);
      this.render();
      EventBus.emit('sources:updated', this.sources);
      this.hideModal();
    } catch (err) {
      this.urlStatus.textContent = 'Error: ' + err.message;
      this.urlStatus.style.color = '#d93025';
    } finally {
      this.btnImportUrl.disabled = false;
    }
  }

  async fetchSources() {
    try {
      const data = await api.get('/sources');
      this.sources = data.sources || [];
      this.render();
    } catch (e) {
      console.error('Failed to fetch sources', e);
    }
  }

  async handleFiles(files) {
    for (const file of Array.from(files)) {
      await this.uploadFile(file);
    }
    this.hideModal();
  }

  async uploadFile(file) {
    const reader = new FileReader();
    reader.onload = async (e) => {
      const content = e.target.result;
      const type = file.type === 'application/pdf' ? 'pdf' : (file.type.startsWith('text/') ? 'text' : 'unknown');
      
      if (type === 'unknown') {
        alert('Unsupported file type. Please upload PDF or Plain Text.');
        return;
      }

      const payload = {
        name: file.name,
        type: type,
        content: content.split(',')[1] || content // Handle base64 for PDF
      };

      try {
        const source = await api.post('/sources', payload);
        this.sources.push(source);
        this.render();
        EventBus.emit('sources:updated', this.sources);
      } catch (err) {
        console.error('Upload failed', err);
        alert('Upload failed: ' + err.message);
      }
    };

    if (file.type === 'application/pdf') {
      reader.readAsDataURL(file);
    } else {
      reader.readAsText(file);
    }
  }

  async toggleSource(id) {
    const source = this.sources.find(s => s.id === id);
    if (!source) return;

    const newActive = !source.active;
    try {
      await api.patch(`/sources/${id}`, { active: newActive });
      source.active = newActive;
      this.render();
      EventBus.emit('sources:updated', this.sources);
    } catch (err) {
      console.error('Toggle failed', err);
    }
  }

  async deleteSource(id) {
    if (!confirm('Are you sure you want to delete this source?')) return;

    try {
      await api.delete(`/sources/${id}`);
      this.sources = this.sources.filter(s => s.id !== id);
      this.render();
      EventBus.emit('sources:updated', this.sources);
    } catch (err) {
      console.error('Delete failed', err);
    }
  }

  render() {
    if (this.sources.length === 0) {
      this.emptyState.style.display = 'block';
      this.container.innerHTML = '';
      return;
    }

    this.emptyState.style.display = 'none';
    this.container.innerHTML = '';
    
    this.sources.forEach(source => {
      const card = this.createSourceCard(source);
      this.container.appendChild(card);
    });
  }

  createSourceCard(source) {
    const card = createElement('div', {
      className: `source-card glass-card ${source.active ? 'active' : ''}`,
      onclick: () => this.toggleSource(source.id)
    }, [
      createElement('div', { className: 'source-toggle' }, [
        source.active ? createElement('div', { style: { width: '6px', height: '6px', backgroundColor: 'white', borderRadius: '1px' } }) : ''
      ]),
      createElement('div', { className: 'source-icon' }, [
        this.getIconForType(source.type)
      ]),
      createElement('div', { className: 'source-info' }, [
        createElement('div', { className: 'source-name' }, source.name),
        createElement('div', { className: 'source-meta' }, `${source.chunk_count || 0} chunks • ${source.word_count || 0} words`)
      ]),
      createElement('div', { className: 'source-actions' }, [
        createElement('button', {
          className: 'btn-icon btn-delete-source',
          onclick: (e) => {
            e.stopPropagation();
            this.deleteSource(source.id);
          }
        }, [
          createElement('svg', { width: '16', height: '16', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: '2' }, [
            createElement('path', { d: 'M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2' })
          ])
        ])
      ])
    ]);

    return card;
  }

  getIconForType(type) {
    const svg = (d) => `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="${d}"/></svg>`;
    const iconMap = {
      pdf: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8',
      text: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z M14 2v6h6 M16 13H8 M16 17H8 M12 9H8',
      url: 'M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71 M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71'
    };
    const div = document.createElement('div');
    div.innerHTML = svg(iconMap[type] || iconMap.text);
    return div.firstChild;
  }
}
