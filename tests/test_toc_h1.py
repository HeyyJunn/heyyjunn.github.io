from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TocH1OverrideTests(unittest.TestCase):
    def test_toc_status_accepts_author_heading_levels_and_keeps_opt_out(self) -> None:
        source = (ROOT / "_includes/toc-status.html").read_text(encoding="utf-8")
        self.assertIn("site.toc and page.toc", source)
        for level in range(1, 5):
            self.assertIn(f"page.content contains '<h{level}'", source)

    def test_tocbot_patch_runs_before_chirpy_layout_bundle(self) -> None:
        source = (ROOT / "_includes/js-selector.html").read_text(encoding="utf-8")
        self.assertIn("{% if enable_toc %}", source)
        self.assertIn("site.data.origin[type].toc.js", source)
        self.assertLess(source.index("toc-heading-levels.js"), source.index("/assets/js/dist/{{ js }}.min.js"))

    def test_patch_extends_existing_tocbot_options_without_vendoring_theme_bundle(self) -> None:
        source = (ROOT / "assets/js/toc-heading-levels.js").read_text(encoding="utf-8")
        self.assertIn("'h1, h2, h3, h4'", source)
        self.assertIn("options.contentSelector !== '.content'", source)
        self.assertIn("['init', 'refresh']", source)
        self.assertFalse((ROOT / "assets/js/dist/post.min.js").exists())

    def test_runtime_patch_preserves_options_and_updates_init_and_refresh(self) -> None:
        patch = ROOT / "assets/js/toc-heading-levels.js"
        harness = f"""
          const calls = [];
          const originalTocbot = {{ calls }};
          Object.defineProperties(originalTocbot, {{
            init: {{
              configurable: false,
              get() {{ return (options) => calls.push(['init', options]); }}
            }},
            refresh: {{
              configurable: false,
              get() {{ return (options) => calls.push(['refresh', options]); }}
            }}
          }});
          global.window = {{ tocbot: originalTocbot }};
          require({str(patch)!r});
          if (window.tocbot === originalTocbot) process.exit(6);
          window.tocbot.init({{
            tocSelector: '#toc', contentSelector: '.content',
            ignoreSelector: '[data-toc-skip]', headingsOffset: 32
          }});
          window.tocbot.refresh({{
            tocSelector: '#toc-popup-content', contentSelector: '.content',
            ignoreSelector: '[data-toc-skip]', collapseDepth: 4
          }});
          if (calls.length !== 2) process.exit(1);
          for (const [, options] of calls) {{
            if (options.headingSelector !== 'h1, h2, h3, h4') process.exit(2);
            if (options.ignoreSelector !== '[data-toc-skip]') process.exit(3);
          }}
          if (calls[0][1].headingsOffset !== 32) process.exit(4);
          if (calls[1][1].collapseDepth !== 4) process.exit(5);
        """
        subprocess.run(["node", "-e", harness], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
