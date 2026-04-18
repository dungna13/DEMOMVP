import { createElement } from '../utils/dom.js';

export class CitationEngine {
  /**
   * Parse [1], [2] patterns and replace with interactive badges.
   * Also strips the ```citations...``` block from the output.
   */
  static parseCitations(text, citations) {
    // 1. Strip the citations block (even if not finished)
    let processedText = text;
    const citBlockIndex = processedText.indexOf('```citations');
    if (citBlockIndex !== -1) {
      processedText = processedText.substring(0, citBlockIndex).trim();
    }

    if (!citations || citations.length === 0) return { text: processedText };

    // 2. Replace [N] with HTML markers for post-processing
    citations.forEach(cit => {
      const pattern = new RegExp(`\\[${cit.id}\\]`, 'g');
      processedText = processedText.replace(pattern, `<span class="cit-placeholder" data-id="${cit.id}"></span>`);
    });

    return { text: processedText };
  }

  /**
   * Inject actual badges into the DOM after markdown rendering
   */
  static injectBadges(container, citations) {
    const placeholders = container.querySelectorAll('.cit-placeholder');
    placeholders.forEach(ph => {
      const id = parseInt(ph.dataset.id);
      const cit = citations.find(c => c.id === id);
      if (cit) {
        const badge = this.createBadge(cit);
        ph.parentNode.replaceChild(badge, ph);
      } else {
        ph.innerText = `[${id}]`;
      }
    });
  }

  static createBadge(cit) {
    const badge = createElement('span', {
      className: 'citation-badge',
      onclick: (e) => {
        e.stopPropagation();
        this.highlightSource(cit);
      }
    }, `${cit.id}`);

    const tooltip = createElement('div', { className: 'citation-tooltip' }, [
      createElement('span', { className: 'tooltip-source' }, cit.source_name || 'Source'),
      createElement('span', { className: 'tooltip-text' }, cit.text)
    ]);

    badge.appendChild(tooltip);
    return badge;
  }

  static highlightSource(cit) {
    // Scroll viewer to reader tab and highlight
    // This will be handled by EventBus
    window.docMind.switchTab('reader');
    // We would need to load the document text here and scroll to the chunk
    console.log('Highlighting citation', cit);
  }
}
