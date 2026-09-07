# Home owner-workflow verification

Synthetic fixture only. Run `python3 tests/browser_smoke.py` with Chrome available (or `CHROME` pointing to its executable). The harness uses an isolated profile and a temporary Brain, not a personal repository.

Verified locally on 7 September 2026:

| Viewport | Overview | Resources | Needs review |
| --- | --- | --- | --- |
| 1440 × 1000 | pass | pass | pass |
| 1920 × 800 | pass | pass | pass |
| 390 × 844 | pass | pass | pass |
| 430 × 1100 | pass | pass | pass |

Real-page checks cover rendering, document overflow, inert injected resource markup, expanded source disclosure, proposal/dismiss behavior, empty search, reduced motion and runtime exceptions. Screenshots, including expanded resources and handoffs, are generated under ignored `.impeccable/review/` and were inspected on desktop and mobile.

Finish review preserved the existing graph-first composition, restrained graphite/violet system and mobile topic list. Corrections made during review: reduced graph label collisions, kept selected mobile navigation visible, wrapped long citations, corrected singular resource copy, and included textarea focus styling. New actions retain 44px minimum targets; source text and proposals never execute.

This is scoped browser verification, not a comprehensive accessibility certification or Lighthouse result. The Impeccable static detector ran in degraded regex mode because its optional parser dependencies were unavailable. Its token findings mostly concern incumbent graph literals and compact type; they are not proof of computed contrast failures or a clean audit. Full assistive-technology testing and broad legacy-token cleanup remain separate follow-up work.
