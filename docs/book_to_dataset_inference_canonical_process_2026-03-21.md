# Book To Dataset To Inference: Canonical Process

This is the canonical process for all further book-processing and note-generation work.

## Mandatory 10-Point Checklist

1. Extract from a book pairs: `notation + content`.
2. Run `content` through `spaCy` and build a `contract tree`.
3. Run `notation` through analysis too and convert it into `template text` with placeholders.
4. Placeholders may reference only attributes from the contract built from the paired content.
5. Build dataset rows from this pair: `contract/template input` + `notation template target`.
6. Train the model on templated notation, not on final rendered note text.
7. At inference time, new content goes through `spaCy -> contract`.
8. The model outputs a notation template with allowed placeholders only.
9. Fill placeholder slot values from the contract.
10. Save the final rendered note back into the contract tree.

## Working Rules

- The book is primary; the current registry is secondary.
- Do not narrow extraction early to only what already fits the current template inventory.
- First extract `notation + content` from the book as fully as possible.
- Only after extraction do normalization, placeholder templating, and dataset conversion.
- `Word` follows the same principle: extract `notation + content`, build structure for content, template the notation.

## Operational Reminder

Before any new book-processing step, re-check the 10-point checklist above and confirm that the current implementation still follows it.
