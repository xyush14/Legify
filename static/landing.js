/* =========================================================================
   Headnote — landing animations
   - IntersectionObserver: fade-up reveal on scroll for [data-reveal]
   - Hero image: subtle Y-axis parallax tied to scroll
   - Nav: solid background once user scrolls past hero
   - Stagger reveals so groups don't pop in all at once
   ========================================================================= */

(() => {
  'use strict';

  // ---------- Reduce-motion guard ----------
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduceMotion) {
    document.querySelectorAll('[data-reveal]').forEach(el => el.classList.add('is-visible'));
    return;
  }

  // ---------- Scroll reveal ----------
  const revealEls = document.querySelectorAll('[data-reveal]');

  // Stagger reveals: assign each visible element a small per-group delay so
  // siblings don't pop simultaneously. Groups are determined by their parent.
  const groupDelays = new WeakMap();
  revealEls.forEach(el => {
    const parent = el.parentElement;
    const idx = groupDelays.get(parent) ?? 0;
    el.style.transitionDelay = `${Math.min(idx * 80, 320)}ms`;
    groupDelays.set(parent, idx + 1);
  });

  const io = new IntersectionObserver(
    entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    },
    {
      root: null,
      rootMargin: '0px 0px -8% 0px',
      threshold: 0.08,
    }
  );

  // First-render: anything already in view at load reveals immediately,
  // without requiring scroll motion.
  requestAnimationFrame(() => {
    revealEls.forEach(el => {
      const r = el.getBoundingClientRect();
      const inView = r.top < window.innerHeight * 0.92 && r.bottom > 0;
      if (inView) {
        el.classList.add('is-visible');
      } else {
        io.observe(el);
      }
    });
  });

  // ---------- Hero image parallax (subtle, GPU-friendly) ----------
  const heroFrame = document.querySelector('.hero__imageFrame');
  if (heroFrame) {
    let raf = null;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        const r = heroFrame.getBoundingClientRect();
        const visibleCenter = r.top + r.height / 2 - window.innerHeight / 2;
        // limit to ±18px so the effect is sleek, not lurchy
        const offset = Math.max(-18, Math.min(18, -visibleCenter * 0.04));
        heroFrame.style.setProperty('transform', `translate3d(0, ${offset}px, 0)`);
        raf = null;
      });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // ---------- Nav background on scroll ----------
  const nav = document.querySelector('.nav');
  if (nav) {
    let lastIsScrolled = false;
    const onScrollNav = () => {
      const scrolled = window.scrollY > 24;
      if (scrolled !== lastIsScrolled) {
        nav.classList.toggle('is-scrolled', scrolled);
        lastIsScrolled = scrolled;
      }
    };
    window.addEventListener('scroll', onScrollNav, { passive: true });
    onScrollNav();
  }

  // ---------- Smooth scroll for in-page anchors ----------
  document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', e => {
      const id = a.getAttribute('href');
      if (id === '#') return;
      const target = document.querySelector(id);
      if (!target) return;
      e.preventDefault();
      const top = target.getBoundingClientRect().top + window.scrollY - 64;
      window.scrollTo({ top, behavior: 'smooth' });
    });
  });

  // ---------- Tiny: stop image's CSS transition once parallax kicks in ----------
  // (hero__imageFrame had a transition for the reveal slide-in; we want
  // parallax to be jitter-free afterward)
  if (heroFrame) {
    heroFrame.addEventListener('transitionend', () => {
      heroFrame.style.transition = 'none';
    }, { once: true });
  }

})();
