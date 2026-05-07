# Pull Request

## Summary

<!-- One-paragraph description of the change. -->

## Evidence (required — AI cannot self-certify)

- [ ] CI quality gate green: `validation`, `nlu corpus`, `token×chain matrix`, `regressions`, existing detector tests.
- [ ] If a tester or user reported a bug that motivated this PR, a regression fixture has been added at `tests/regressions/screenshots.yaml`.
- [ ] If a new intent / phrasing pattern is supported, the NLU corpus at `tests/nlu/corpus.yaml` has new adversarial entries.
- [ ] Manual smoke test on staging deployment. Paste deployment URL + repro link below.
- [ ] `gitnexus_detect_changes` reviewed; affected processes acceptable.

## Tester sign-off (required for production-affecting changes)

- [ ] Tester: ____ has run the change against the live build at https://ilyonai.com or staging, signed off below.

## Risk

<!-- Describe blast radius. List any HIGH/CRITICAL impact warnings. -->

## Notes

<!-- Anything reviewers should look at first. -->
