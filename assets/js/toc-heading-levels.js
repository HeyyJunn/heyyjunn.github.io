(() => {
  'use strict';

  const originalTocbot = window.tocbot;
  if (!originalTocbot || originalTocbot.__chirpyH1Patched) {
    return;
  }

  const headingSelector = 'h1, h2, h3, h4';
  const withAuthorHeadingLevels = (options) => {
    if (!options || options.contentSelector !== '.content') {
      return options;
    }

    return { ...options, headingSelector };
  };

  // Tocbot 4 exposes init/refresh as non-configurable getters. Inherit from
  // the original export object and override the methods on a small wrapper
  // instead of modifying the library or Chirpy's compiled post bundle.
  const wrappedTocbot = Object.create(originalTocbot);
  for (const method of ['init', 'refresh']) {
    Object.defineProperty(wrappedTocbot, method, {
      value(options, ...rest) {
        return originalTocbot[method].call(
          originalTocbot,
          withAuthorHeadingLevels(options),
          ...rest
        );
      }
    });
  }

  Object.defineProperty(wrappedTocbot, '__chirpyH1Patched', { value: true });
  window.tocbot = wrappedTocbot;
})();
