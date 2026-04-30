# Current Task

Build the dataset so that:

- `input` is always templated with placeholders.
- `target` is templated with the same placeholders when possible.
- if `target` cannot be templated cleanly, keep `target` raw.
- do not use raw `input` for templated rows.
- only `input` and `target` belong in the training JSONL.

Pipeline target:

1. Take a `sentence + note` pair.
2. Template the `input` with placeholders.
3. Template the `target` with the same placeholders when possible.
4. If `target` cannot be templated, keep it raw.
5. Train on `input -> target`.
6. Infer the same way.
7. Post-process placeholders only when the model output is templated.

Required report after each dataset build:

- total rows
- template rows
- raw rows
- counts and shares for template/raw
- unique `input`
- unique `target`
- split sizes
- examples of real `input -> target` pairs
- note whether `input` and `target` are templated or raw for the shown examples

Do not mix:

- raw `input` with templated `target`
- templated `input` with raw `target` unless templating the target is impossible
