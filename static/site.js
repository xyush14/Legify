/* Headnote — shared site behaviour: Book a Demo (Calendly popup) + nav state */
(function(){
  window.CALENDLY_URL = "https://calendly.com/hello-headnote/headnote-demo";
  window.bookDemo = function(e){
    if(e && e.preventDefault) e.preventDefault();
    if(window.Calendly && typeof window.Calendly.initPopupWidget === 'function'){
      window.Calendly.initPopupWidget({ url: window.CALENDLY_URL });
    } else {
      window.location.href = "/contact";   // fallback if Calendly hasn't loaded
    }
    return false;
  };
  function onScroll(){ var n=document.querySelector('.site-nav'); if(n) n.classList.toggle('scrolled', window.scrollY>12); }
  window.addEventListener('scroll', onScroll, {passive:true}); onScroll();
})();
