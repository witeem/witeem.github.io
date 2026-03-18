// Theme toggle
(function () {
  const THEME_KEY = 'witeem-theme';
  const btn = document.getElementById('themeToggle');
  const mobileBtn = document.getElementById('mobileMenuBtn');
  const mobileNav = document.getElementById('mobileNav');

  // Init theme
  const saved = localStorage.getItem(THEME_KEY) ||
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', saved);

  // Toggle theme
  if (btn) {
    btn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem(THEME_KEY, next);
    });
  }

  // Mobile menu
  if (mobileBtn && mobileNav) {
    mobileBtn.addEventListener('click', () => {
      mobileNav.classList.toggle('open');
    });
  }

  // Active nav link
  const navLinks = document.querySelectorAll('.nav-link');
  navLinks.forEach(link => {
    if (link.getAttribute('href') === window.location.pathname ||
        (window.location.pathname.startsWith(link.getAttribute('href')) &&
         link.getAttribute('href') !== '/')) {
      link.classList.add('active');
    }
  });

  // Smooth scroll for TOC
  document.querySelectorAll('.toc a').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const target = document.querySelector(link.getAttribute('href'));
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  // Copy code button
  document.querySelectorAll('pre').forEach(pre => {
    const btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.textContent = '复制';
    btn.style.cssText = `
      position: absolute; top: 0.75rem; right: 0.75rem;
      background: rgba(255,255,255,0.1); color: #cdd6f4;
      border: 1px solid rgba(255,255,255,0.2); border-radius: 4px;
      padding: 0.2rem 0.5rem; font-size: 0.75rem; cursor: pointer;
      font-family: inherit; transition: all 0.2s;
    `;
    pre.style.position = 'relative';
    pre.appendChild(btn);

    btn.addEventListener('click', () => {
      const code = pre.querySelector('code');
      if (code) {
        navigator.clipboard.writeText(code.textContent || '').then(() => {
          btn.textContent = '已复制!';
          btn.style.background = 'rgba(99,102,241,0.3)';
          setTimeout(() => {
            btn.textContent = '复制';
            btn.style.background = 'rgba(255,255,255,0.1)';
          }, 2000);
        });
      }
    });
  });

  // Reading progress bar
  const progressBar = document.createElement('div');
  progressBar.style.cssText = `
    position: fixed; top: 0; left: 0; height: 3px; width: 0%;
    background: linear-gradient(90deg, #6366f1, #06b6d4);
    z-index: 9999; transition: width 0.1s;
  `;
  document.body.appendChild(progressBar);

  window.addEventListener('scroll', () => {
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const progress = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
    progressBar.style.width = progress + '%';
  });
})();
