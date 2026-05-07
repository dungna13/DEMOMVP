// app.js — Search UX enhancements

document.addEventListener('DOMContentLoaded', () => {

  // ── Hint chips → fill search input ──────────────────────────
  document.querySelectorAll('.search-hint-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const input = document.querySelector('.search-input');
      if (input) {
        input.value = chip.textContent.trim();
        input.focus();
      }
    });
  });

  // ── Auto-submit facet links (giữ query) ──────────────────────
  // Handled via <a> links in template, no JS needed

  // ── Loading state on search submit ──────────────────────────
  const form = document.querySelector('#search-form');
  if (form) {
    form.addEventListener('submit', () => {
      const btn = form.querySelector('.search-btn');
      if (btn) {
        btn.textContent = 'Đang tìm...';
        btn.style.opacity = '0.7';
      }
    });
  }

  // ── Smooth highlight animation ───────────────────────────────
  document.querySelectorAll('mark').forEach(m => {
    m.style.transition = 'background 0.3s';
  });

  // ── Keyboard shortcut: / to focus search ────────────────────
  document.addEventListener('keydown', e => {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
      e.preventDefault();
      const input = document.querySelector('.search-input');
      if (input) input.focus();
    }
    if (e.key === 'Escape') {
      const input = document.querySelector('.search-input');
      if (input) input.blur();
    }
  });

  // ── Counter animation for stats ──────────────────────────────
  document.querySelectorAll('.stat-value[data-count]').forEach(el => {
    const target = parseInt(el.dataset.count, 10);
    if (isNaN(target)) return;
    let current = 0;
    const step = Math.ceil(target / 30);
    const timer = setInterval(() => {
      current = Math.min(current + step, target);
      el.textContent = current.toLocaleString('vi-VN');
      if (current >= target) clearInterval(timer);
    }, 30);
  });

  // ── Fade in cards on scroll ──────────────────────────────────
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'translateY(0)';
        }
      });
    }, { threshold: 0.05 });

    document.querySelectorAll('.doc-card, .section-card').forEach(card => {
      observer.observe(card);
    });
  }
});
