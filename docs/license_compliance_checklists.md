# License Compliance Checklists

Last updated: 2026-02-17

Source of truth for component licenses: `docs/licenses_inventory.md`.

## Pre-Merge Checklist (for any new dependency/model/tool/data source)

- [ ] Component is added to `docs/licenses_inventory.md` with:
  - name/version
  - license type
  - source URL
  - usage context in this project
- [ ] Deployment mode impact is recorded (`backend-only` vs `distributed/on-prem`).
- [ ] License compatibility for commercial path is explicitly confirmed.
- [ ] If license is copyleft (for example GPL), feature is marked as requiring release legal gate for distributed delivery.

## Release Checklist (mandatory before production release)

- [ ] All new dependencies/models since previous release are present in `docs/licenses_inventory.md`.
- [ ] Non-commercial licenses (`CC-BY-NC-*`, similar) are excluded from commercial production path.
- [ ] Copyleft components (if any) have deployment mode decision recorded.
- [ ] For on-prem/distributed release artifacts:
  - legal/compliance review is completed and approved.
- [ ] For backend-only/SaaS release:
  - license inventory reviewed and approved by maintainer.

## Phonetic Backend Gate (GPL-sensitive)

When phonetics is enabled in production with GPL-backed tools (`espeak-ng`, etc.):

- [ ] component/version/license/source recorded in `docs/licenses_inventory.md`
- [ ] deployment mode explicitly declared in release notes
- [ ] legal gate passed for any distributed/on-prem delivery

Recommended command (must pass before production enablement):
```bash
.venv/bin/python -m ela_pipeline.runtime.license_gate \
  --feature phonetic \
  --deployment-mode distributed \
  --phonetic-policy enabled \
  --legal-approval
```
