# Template-ID Dataset Report (2026-02-13)

## Build command

```bash
source .venv/bin/activate
python -m ela_pipeline.dataset.build_dataset \
  --input linguistic_hierarchical_3000_v3.json \
  --output-dir data/processed_template_id \
  --use-template-id-targets \
  --no-use-reference-templates \
  --seed 42
```

## Key results

- Output dir: `data/processed_template_id`
- Total rows after balance: `511`
- Unique targets after balance: `10`
- Duplicate ratio after balance: `0.980431`
- Active template IDs after balance: `10 / 19`

## Comparison vs reference dataset

Source: `data/processed_reference/stats.json` vs `data/processed_template_id/stats.json`

- Reference total after balance: `708`
- Reference unique targets after balance: `110`
- Reference duplicate ratio after balance: `0.844633`
- Template-ID total after balance: `511`
- Template-ID unique targets after balance: `10`
- Template-ID duplicate ratio after balance: `0.980431`

## Conclusion

- Template-ID mode is wired and deterministic, but target diversity is currently too low for robust training.
- Next required step before retraining: improve template mapping/note variants to increase active template coverage and reduce duplicate concentration.
