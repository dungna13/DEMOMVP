import { SourceManager } from './modules/SourceManager.js';
import { SourceViewer } from './modules/SourceViewer.js';
import { ChatEngine } from './modules/ChatEngine.js';

class App {
  constructor() {
    this.state = {
      sources: [],
      activeSources: [],
      currentTab: 'summary'
    };
    
    this.init();
  }

  async init() {
    console.log('DocMind initializing...');
    
    // Initialize modules in order
    this.sourceManager = new SourceManager();
    this.sourceViewer = new SourceViewer();
    this.chatEngine = new ChatEngine();

    this.bindEvents();
  }

  bindEvents() {
    // Listen for tab changes
    const tabs = document.querySelectorAll('.tab-item');
    tabs.forEach(tab => {
      tab.onclick = () => {
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        
        const tabName = tab.dataset.tab;
        this.switchTab(tabName);
      };
    });
  }

  switchTab(tabName) {
    const summaryContainer = document.getElementById('summary-container');
    const readerContainer = document.getElementById('reader-container');

    if (tabName === 'summary') {
      summaryContainer.style.display = 'block';
      readerContainer.style.display = 'none';
    } else {
      summaryContainer.style.display = 'none';
      readerContainer.style.display = 'block';
    }
    
    this.state.currentTab = tabName;
  }
}

// Global initialization
window.addEventListener('DOMContentLoaded', () => {
  window.docMind = new App();
});
