function adjustContentHeight() {
    const footer = document.querySelector('footer');
    const contentWrapper = document.querySelector('.content-wrapper');
    
    if (footer && contentWrapper) {
      const footerHeight = footer.offsetHeight;
      contentWrapper.style.minHeight = `calc(100vh - ${footerHeight}px)`;
    }
  }
  
  // Run on page load
  window.addEventListener('load', adjustContentHeight);
  
  // Run when window is resized (for responsive layouts)
  window.addEventListener('resize', adjustContentHeight);