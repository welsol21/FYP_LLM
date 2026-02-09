# Curator Summary Report

The ELA Linguistic Notes Pipeline has been stabilized and brought to a production-ready baseline.

## Summary
The project now produces contract-compliant linguistic JSON with improved structural consistency, clearer linguistic annotations, and stronger validation control.

## Key Outcomes
1. The data contract was upgraded and formalized (v2-compatible), with backward-safe operation.
2. The pipeline quality improved: less noisy phrases, better fallback notes, and more interpretable outputs.
3. Validation became stricter and more reliable, including support for both standard and strict modes.
4. Test coverage was expanded, reducing regression risk and improving confidence in releases.
5. Documentation was synchronized with the implemented behavior and CLI usage.

## Practical Result
Compared to the initial state, outputs are now cleaner, easier to consume downstream, and easier to debug when quality issues appear.

## Appendix A: Contract Schema (Verbatim)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/linguistic_contract.schema.json",
  "title": "ELA Linguistic Contract",
  "type": "object",
  "additionalProperties": {
    "$ref": "#/$defs/sentenceNode"
  },
  "$defs": {
    "wordNode": {
      "type": "object",
      "required": ["type", "content", "tense", "linguistic_notes", "part_of_speech", "linguistic_elements"],
      "properties": {
        "type": {"const": "Word"},
        "content": {"type": "string"},
        "tense": {"type": "string"},
        "linguistic_notes": {"type": "array", "items": {"type": "string"}},
        "part_of_speech": {"type": "string"},
        "linguistic_elements": {"type": "array", "maxItems": 0}
      },
      "additionalProperties": true
    },
    "phraseNode": {
      "type": "object",
      "required": ["type", "content", "tense", "linguistic_notes", "part_of_speech", "linguistic_elements"],
      "properties": {
        "type": {"const": "Phrase"},
        "content": {"type": "string"},
        "tense": {"type": "string"},
        "linguistic_notes": {"type": "array", "items": {"type": "string"}},
        "part_of_speech": {"type": "string"},
        "linguistic_elements": {
          "type": "array",
          "items": {"$ref": "#/$defs/wordNode"}
        }
      },
      "additionalProperties": true
    },
    "sentenceNode": {
      "type": "object",
      "required": ["type", "content", "tense", "linguistic_notes", "part_of_speech", "linguistic_elements"],
      "properties": {
        "type": {"const": "Sentence"},
        "content": {"type": "string"},
        "tense": {"type": "string"},
        "linguistic_notes": {"type": "array", "items": {"type": "string"}},
        "part_of_speech": {"type": "string"},
        "linguistic_elements": {
          "type": "array",
          "items": {"$ref": "#/$defs/phraseNode"}
        }
      },
      "additionalProperties": true
    }
  }
}
```

## Appendix B: Contract Example (Verbatim)

```json
{
  "She should have trusted her instincts before making the decision.": {
    "type": "Sentence",
    "content": "She should have trusted her instincts before making the decision.",
    "tense": "past perfect",
    "linguistic_notes": [
      "This sentence uses a modal verb 'should' followed by a perfect infinitive 'have trusted' to express a past recommendation or regret."
    ],
    "part_of_speech": "sentence",
    "linguistic_elements": [
      {
        "type": "Phrase",
        "content": "She should have trusted her instincts",
        "tense": "past perfect",
        "linguistic_notes": [
          "This phrase uses a modal verb 'should' with a perfect infinitive to express a past action that was advisable."
        ],
        "part_of_speech": "verb phrase",
        "linguistic_elements": [
          {
            "type": "Word",
            "content": "She",
            "tense": "null",
            "linguistic_notes": [
              "A pronoun used to refer to a female person or animal previously mentioned or easily identified."
            ],
            "part_of_speech": "pronoun",
            "linguistic_elements": []
          },
          {
            "type": "Word",
            "content": "should",
            "tense": "null",
            "linguistic_notes": [
              "A modal verb used to indicate obligation, duty, or correctness, typically when criticizing someone's actions."
            ],
            "part_of_speech": "modal verb",
            "linguistic_elements": []
          },
          {
            "type": "Word",
            "content": "have",
            "tense": "null",
            "linguistic_notes": [
              "An auxiliary verb used with past participles to form perfect tenses."
            ],
            "part_of_speech": "auxiliary verb",
            "translations": ["иметь"],
            "linguistic_elements": []
          },
          {
            "type": "Word",
            "content": "trusted",
            "tense": "past participle",
            "linguistic_notes": [
              "The past participle form of the verb 'trust', used to express a completed action."
            ],
            "part_of_speech": "verb",
            "linguistic_elements": []
          },
          {
            "type": "Word",
            "content": "her",
            "tense": "null",
            "linguistic_notes": [
              "A pronoun used to refer to a female person or animal previously mentioned or easily identified."
            ],
            "part_of_speech": "pronoun",
            "linguistic_elements": []
          },
          {
            "type": "Word",
            "content": "instincts",
            "tense": "null",
            "linguistic_notes": [
              "A noun referring to an innate, typically fixed pattern of behavior in animals in response to certain stimuli."
            ],
            "part_of_speech": "noun",
            "linguistic_elements": []
          }
        ]
      },
      {
        "type": "Phrase",
        "content": "before making the decision",
        "tense": "null",
        "linguistic_notes": [
          "This phrase indicates the time frame in which the action should have been completed."
        ],
        "part_of_speech": "prepositional phrase",
        "linguistic_elements": [
          {
            "type": "Word",
            "content": "before",
            "tense": "null",
            "linguistic_notes": [
              "A preposition used to indicate the time or event preceding another."
            ],
            "part_of_speech": "preposition",
            "linguistic_elements": []
          },
          {
            "type": "Word",
            "content": "making",
            "tense": "present participle",
            "linguistic_notes": [
              "The present participle form of the verb 'make', used to form continuous tenses."
            ],
            "part_of_speech": "verb",
            "linguistic_elements": []
          },
          {
            "type": "Word",
            "content": "the",
            "tense": "null",
            "linguistic_notes": [
              "A definite article used to specify a particular noun that is known to the reader or listener."
            ],
            "part_of_speech": "article",
            "linguistic_elements": []
          },
          {
            "type": "Word",
            "content": "decision",
            "tense": "null",
            "linguistic_notes": [
              "A noun referring to a conclusion or resolution reached after consideration."
            ],
            "part_of_speech": "noun",
            "linguistic_elements": []
          }
        ]
      }
    ]
  }
}

```
