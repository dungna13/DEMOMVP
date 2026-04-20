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

    // Mobile Nav Switching
    const mobileNavItems = document.querySelectorAll('.nav-item');
    const panes = document.querySelectorAll('.pane');
    
    // Set default active pane for mobile
    const chatPane = document.getElementById('chat-pane');
    if (chatPane) chatPane.classList.add('active-mobile');

    mobileNavItems.forEach(item => {
      item.onclick = () => {
        const targetPaneId = item.dataset.pane;
        
        // Update Nav UI
        mobileNavItems.forEach(i => i.classList.remove('active'));
        item.classList.add('active');

        // Update Panes UI
        panes.forEach(p => p.classList.remove('active-mobile'));
        const targetPane = document.getElementById(targetPaneId);
        if (targetPane) targetPane.classList.add('active-mobile');
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
