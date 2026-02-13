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

## Appendix A: Contract Schema v2 Strict (Verbatim)

Source: `schemas/linguistic_contract_v2_strict.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/linguistic_contract_v2_strict.schema.json",
  "title": "ELA Linguistic Contract v2 Strict",
  "type": "object",
  "additionalProperties": {
    "$ref": "#/$defs/sentenceNode"
  },
  "$defs": {
    "sourceSpan": {
      "type": "object",
      "required": ["start", "end"],
      "properties": {
        "start": {"type": "integer", "minimum": 0},
        "end": {"type": "integer", "minimum": 0}
      },
      "additionalProperties": false
    },
    "typedNote": {
      "type": "object",
      "required": ["text", "kind", "confidence", "source"],
      "properties": {
        "text": {"type": "string"},
        "kind": {"type": "string", "enum": ["semantic", "syntactic", "morphological", "discourse"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "source": {"type": "string", "enum": ["model", "rule", "fallback"]}
      },
      "additionalProperties": false
    },
    "rejectedCandidateStat": {
      "type": "object",
      "required": ["text", "count", "reasons"],
      "properties": {
        "text": {"type": "string"},
        "count": {"type": "integer", "minimum": 1},
        "reasons": {
          "type": "array",
          "items": {"type": "string"}
        }
      },
      "additionalProperties": false
    },
    "wordNode": {
      "type": "object",
      "required": [
        "type",
        "content",
        "tense",
        "linguistic_notes",
        "part_of_speech",
        "linguistic_elements",
        "node_id",
        "parent_id",
        "source_span",
        "grammatical_role",
        "schema_version"
      ],
      "properties": {
        "type": {"const": "Word"},
        "content": {"type": "string"},
        "tense": {"type": ["string", "null"]},
        "aspect": {"type": ["string", "null"]},
        "mood": {"type": ["string", "null"]},
        "voice": {"type": ["string", "null"]},
        "finiteness": {"type": ["string", "null"]},
        "tam_construction": {"type": "string", "minLength": 1},
        "linguistic_notes": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"$ref": "#/$defs/typedNote"}},
        "quality_flags": {"type": "array", "items": {"type": "string"}},
        "rejected_candidates": {"type": "array", "items": {"type": "string"}},
        "rejected_candidate_stats": {"type": "array", "items": {"$ref": "#/$defs/rejectedCandidateStat"}},
        "reason_codes": {"type": "array", "items": {"type": "string"}},
        "part_of_speech": {"type": "string"},
        "linguistic_elements": {"type": "array", "maxItems": 0},
        "features": {
          "type": "object",
          "additionalProperties": {"type": "string"}
        },
        "node_id": {"type": "string"},
        "parent_id": {"type": "string"},
        "source_span": {"$ref": "#/$defs/sourceSpan"},
        "grammatical_role": {"type": "string"},
        "dep_label": {"type": "string"},
        "head_id": {"type": ["string", "null"]},
        "schema_version": {"type": "string", "const": "v2"}
      },
      "additionalProperties": true
    },
    "phraseNode": {
      "type": "object",
      "required": [
        "type",
        "content",
        "tense",
        "linguistic_notes",
        "part_of_speech",
        "linguistic_elements",
        "node_id",
        "parent_id",
        "source_span",
        "grammatical_role",
        "schema_version"
      ],
      "properties": {
        "type": {"const": "Phrase"},
        "content": {"type": "string"},
        "tense": {"type": ["string", "null"]},
        "aspect": {"type": ["string", "null"]},
        "mood": {"type": ["string", "null"]},
        "voice": {"type": ["string", "null"]},
        "finiteness": {"type": ["string", "null"]},
        "tam_construction": {"type": "string", "minLength": 1},
        "linguistic_notes": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"$ref": "#/$defs/typedNote"}},
        "quality_flags": {"type": "array", "items": {"type": "string"}},
        "rejected_candidates": {"type": "array", "items": {"type": "string"}},
        "rejected_candidate_stats": {"type": "array", "items": {"$ref": "#/$defs/rejectedCandidateStat"}},
        "reason_codes": {"type": "array", "items": {"type": "string"}},
        "part_of_speech": {"type": "string"},
        "linguistic_elements": {
          "type": "array",
          "minItems": 2,
          "items": {"$ref": "#/$defs/wordNode"}
        },
        "node_id": {"type": "string"},
        "parent_id": {"type": "string"},
        "source_span": {"$ref": "#/$defs/sourceSpan"},
        "grammatical_role": {"type": "string"},
        "schema_version": {"type": "string", "const": "v2"}
      },
      "allOf": [
        {
          "if": {
            "properties": {
              "tam_construction": {"const": "modal_perfect"}
            },
            "required": ["tam_construction"]
          },
          "then": {
            "properties": {
              "mood": {"const": "modal"},
              "aspect": {"const": "perfect"},
              "tense": {"type": "null"}
            }
          }
        }
      ],
      "additionalProperties": true
    },
    "sentenceNode": {
      "type": "object",
      "required": [
        "type",
        "content",
        "tense",
        "linguistic_notes",
        "part_of_speech",
        "linguistic_elements",
        "node_id",
        "parent_id",
        "source_span",
        "grammatical_role",
        "schema_version"
      ],
      "properties": {
        "type": {"const": "Sentence"},
        "content": {"type": "string"},
        "tense": {"type": ["string", "null"]},
        "aspect": {"type": ["string", "null"]},
        "mood": {"type": ["string", "null"]},
        "voice": {"type": ["string", "null"]},
        "finiteness": {"type": ["string", "null"]},
        "tam_construction": {"type": "string", "minLength": 1},
        "linguistic_notes": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"$ref": "#/$defs/typedNote"}},
        "quality_flags": {"type": "array", "items": {"type": "string"}},
        "rejected_candidates": {"type": "array", "items": {"type": "string"}},
        "rejected_candidate_stats": {"type": "array", "items": {"$ref": "#/$defs/rejectedCandidateStat"}},
        "reason_codes": {"type": "array", "items": {"type": "string"}},
        "part_of_speech": {"type": "string"},
        "linguistic_elements": {
          "type": "array",
          "items": {"$ref": "#/$defs/phraseNode"}
        },
        "node_id": {"type": "string"},
        "parent_id": {"type": "null"},
        "source_span": {"$ref": "#/$defs/sourceSpan"},
        "grammatical_role": {"type": "string"},
        "schema_version": {"type": "string", "const": "v2"}
      },
      "allOf": [
        {
          "if": {
            "properties": {
              "tam_construction": {"const": "modal_perfect"}
            },
            "required": ["tam_construction"]
          },
          "then": {
            "properties": {
              "mood": {"const": "modal"},
              "aspect": {"const": "perfect"},
              "tense": {"type": "null"}
            }
          }
        }
      ],
      "additionalProperties": true
    }
  }
}
```

## Appendix B: Contract Example (Verbatim, Latest Inference Output)

Source: `inference_results/pipeline_result_2026-02-09_23-09-00.json`

```json
{
  "She should have trusted her instincts before making the decision.": {
    "type": "Sentence",
    "content": "She should have trusted her instincts before making the decision.",
    "tense": "past perfect",
    "aspect": "perfect",
    "mood": "modal",
    "voice": "active",
    "finiteness": "finite",
    "linguistic_notes": [
      "This sentence expresses a complete proposition and is anchored in past perfect time reference, with about 10 lexical items."
    ],
    "notes": [
      {
        "text": "This sentence expresses a complete proposition and is anchored in past perfect time reference, with about 10 lexical items.",
        "kind": "syntactic",
        "confidence": 0.65,
        "source": "fallback"
      }
    ],
    "quality_flags": [
      "fallback_used"
    ],
    "rejected_candidates": [
      "Node type or subject of the clause.",
      "Subordinate clause of concession introduced by a subordinating conjunction."
    ],
    "rejected_candidate_stats": [
      {
        "text": "Node type or subject of the clause.",
        "count": 3,
        "reasons": [
          "MODEL_OUTPUT_LOW_QUALITY"
        ]
      },
      {
        "text": "Subordinate clause of concession introduced by a subordinating conjunction.",
        "count": 1,
        "reasons": [
          "MODEL_OUTPUT_LOW_QUALITY"
        ]
      }
    ],
    "reason_codes": [
      "MODEL_OUTPUT_LOW_QUALITY",
      "FALLBACK_NOTE_ACCEPTED"
    ],
    "schema_version": "v2",
    "part_of_speech": "sentence",
    "linguistic_elements": [
      {
        "type": "Phrase",
        "content": "should have trusted her instincts",
        "tense": "past perfect",
        "aspect": "perfect",
        "mood": "modal",
        "voice": "active",
        "finiteness": "finite",
        "linguistic_notes": [
          "The phrase 'should have trusted her instincts' is a verb phrase encoding an action/state with past perfect temporal interpretation."
        ],
        "notes": [
          {
            "text": "The phrase 'should have trusted her instincts' is a verb phrase encoding an action/state with past perfect temporal interpretation.",
            "kind": "syntactic",
            "confidence": 0.65,
            "source": "fallback"
          }
        ],
        "quality_flags": [
          "fallback_used"
        ],
        "rejected_candidates": [
          "Verb-centred phrase expressing what happens to or about the subject.",
          "Verb phrase expressing what happens to or about the subject."
        ],
        "rejected_candidate_stats": [
          {
            "text": "Verb-centred phrase expressing what happens to or about the subject.",
            "count": 2,
            "reasons": [
              "MODEL_OUTPUT_LOW_QUALITY"
            ]
          },
          {
            "text": "Verb phrase expressing what happens to or about the subject.",
            "count": 1,
            "reasons": [
              "MODEL_NOTE_UNSUITABLE"
            ]
          }
        ],
        "reason_codes": [
          "MODEL_NOTE_UNSUITABLE",
          "FALLBACK_NOTE_ACCEPTED"
        ],
        "schema_version": "v2",
        "part_of_speech": "verb phrase",
        "linguistic_elements": [
          {
            "type": "Word",
            "content": "should",
            "tense": "null",
            "aspect": "simple",
            "mood": "indicative",
            "voice": "active",
            "finiteness": "finite",
            "linguistic_notes": [
              "'should' is an auxiliary verb that supports verbal grammar, modality, or voice interpretation."
            ],
            "notes": [
              {
                "text": "'should' is an auxiliary verb that supports verbal grammar, modality, or voice interpretation.",
                "kind": "morphological",
                "confidence": 0.65,
                "source": "fallback"
              }
            ],
            "quality_flags": [
              "fallback_used"
            ],
            "rejected_candidates": [
              "Sentence: should have trusted her instincts before making the decision."
            ],
            "rejected_candidate_stats": [
              {
                "text": "Sentence: should have trusted her instincts before making the decision.",
                "count": 1,
                "reasons": [
                  "MODEL_NOTE_UNSUITABLE"
                ]
              }
            ],
            "reason_codes": [
              "MODEL_NOTE_UNSUITABLE",
              "FALLBACK_NOTE_ACCEPTED"
            ],
            "schema_version": "v2",
            "part_of_speech": "auxiliary verb",
            "linguistic_elements": [],
            "features": {
              "number": "null",
              "person": "null",
              "case": "null",
              "degree": "null",
              "definiteness": "null",
              "verb_form": "fin",
              "gender": "null",
              "tense_feature": "null"
            },
            "node_id": "n5",
            "parent_id": "n4",
            "source_span": {
              "start": 4,
              "end": 10
            },
            "grammatical_role": "auxiliary",
            "dep_label": "aux",
            "head_id": "n7"
          },
          {
            "type": "Word",
            "content": "have",
            "tense": "null",
            "aspect": "simple",
            "mood": "null",
            "voice": "active",
            "finiteness": "non-finite",
            "linguistic_notes": [
              "'have' is an auxiliary verb that supports verbal grammar, modality, or voice interpretation."
            ],
            "notes": [
              {
                "text": "'have' is an auxiliary verb that supports verbal grammar, modality, or voice interpretation.",
                "kind": "morphological",
                "confidence": 0.65,
                "source": "fallback"
              }
            ],
            "quality_flags": [
              "fallback_used"
            ],
            "rejected_candidates": [
              "Sentence is a nod to the subject of the clause."
            ],
            "rejected_candidate_stats": [
              {
                "text": "Sentence is a nod to the subject of the clause.",
                "count": 1,
                "reasons": [
                  "MODEL_NOTE_UNSUITABLE"
                ]
              }
            ],
            "reason_codes": [
              "MODEL_NOTE_UNSUITABLE",
              "FALLBACK_NOTE_ACCEPTED"
            ],
            "schema_version": "v2",
            "part_of_speech": "auxiliary verb",
            "linguistic_elements": [],
            "features": {
              "number": "null",
              "person": "null",
              "case": "null",
              "degree": "null",
              "definiteness": "null",
              "verb_form": "inf",
              "gender": "null",
              "tense_feature": "null"
            },
            "node_id": "n6",
            "parent_id": "n4",
            "source_span": {
              "start": 11,
              "end": 15
            },
            "grammatical_role": "auxiliary",
            "dep_label": "aux",
            "head_id": "n7"
          },
          {
            "type": "Word",
            "content": "trusted",
            "tense": "past participle",
            "aspect": "perfect",
            "mood": "null",
            "voice": "active",
            "finiteness": "non-finite",
            "linguistic_notes": [
              "'trusted' is a past participle that often contributes perfect or passive verbal constructions."
            ],
            "notes": [
              {
                "text": "'trusted' is a past participle that often contributes perfect or passive verbal constructions.",
                "kind": "semantic",
                "confidence": 0.65,
                "source": "fallback"
              }
            ],
            "quality_flags": [
              "fallback_used"
            ],
            "rejected_candidates": [
              "Sentence is a nod to the subject of the clause."
            ],
            "rejected_candidate_stats": [
              {
                "text": "Sentence is a nod to the subject of the clause.",
                "count": 1,
                "reasons": [
                  "MODEL_NOTE_UNSUITABLE"
                ]
              }
            ],
            "reason_codes": [
              "MODEL_NOTE_UNSUITABLE",
              "FALLBACK_NOTE_ACCEPTED"
            ],
            "schema_version": "v2",
            "part_of_speech": "verb",
            "linguistic_elements": [],
            "features": {
              "number": "null",
              "person": "null",
              "case": "null",
              "degree": "null",
              "definiteness": "null",
              "verb_form": "part",
              "gender": "null",
              "tense_feature": "past"
            },
            "node_id": "n7",
            "parent_id": "n4",
            "source_span": {
              "start": 16,
              "end": 23
            },
            "grammatical_role": "predicate",
            "dep_label": "ROOT",
            "head_id": null
          },
          {
            "type": "Word",
            "content": "her",
            "tense": "null",
            "aspect": "null",
            "mood": "null",
            "voice": "null",
            "finiteness": "null",
            "linguistic_notes": [
              "'her' is a pronoun used to refer to an entity without repeating a full noun phrase."
            ],
            "notes": [
              {
                "text": "'her' is a pronoun used to refer to an entity without repeating a full noun phrase.",
                "kind": "syntactic",
                "confidence": 0.65,
                "source": "fallback"
              }
            ],
            "quality_flags": [
              "fallback_used"
            ],
            "rejected_candidates": [
              "Sentence is a nod to her instincts."
            ],
            "rejected_candidate_stats": [
              {
                "text": "Sentence is a nod to her instincts.",
                "count": 1,
                "reasons": [
                  "MODEL_NOTE_UNSUITABLE"
                ]
              }
            ],
            "reason_codes": [
              "MODEL_NOTE_UNSUITABLE",
              "FALLBACK_NOTE_ACCEPTED"
            ],
            "schema_version": "v2",
            "part_of_speech": "pronoun",
            "linguistic_elements": [],
            "features": {
              "number": "sing",
              "person": "3",
              "case": "null",
              "degree": "null",
              "definiteness": "null",
              "verb_form": "null",
              "gender": "fem",
              "tense_feature": "null"
            },
            "node_id": "n8",
            "parent_id": "n4",
            "source_span": {
              "start": 24,
              "end": 27
            },
            "grammatical_role": "other",
            "dep_label": "poss",
            "head_id": "n9"
          },
          {
            "type": "Word",
            "content": "instincts",
            "tense": "null",
            "aspect": "null",
            "mood": "null",
            "voice": "null",
            "finiteness": "null",
            "linguistic_notes": [
              "'instincts' is a noun that names an entity, concept, or object in context."
            ],
            "notes": [
              {
                "text": "'instincts' is a noun that names an entity, concept, or object in context.",
                "kind": "syntactic",
                "confidence": 0.65,
                "source": "fallback"
              }
            ],
            "quality_flags": [
              "fallback_used"
            ],
            "rejected_candidates": [
              "Sentence is a noun used as the subject of the clause."
            ],
            "rejected_candidate_stats": [
              {
                "text": "Sentence is a noun used as the subject of the clause.",
                "count": 1,
                "reasons": [
                  "MODEL_NOTE_UNSUITABLE"
                ]
              }
            ],
            "reason_codes": [
              "MODEL_NOTE_UNSUITABLE",
              "FALLBACK_NOTE_ACCEPTED"
            ],
            "schema_version": "v2",
            "part_of_speech": "noun",
            "linguistic_elements": [],
            "features": {
              "number": "plur",
              "person": "null",
              "case": "null",
              "degree": "null",
              "definiteness": "null",
              "verb_form": "null",
              "gender": "null",
              "tense_feature": "null"
            },
            "node_id": "n9",
            "parent_id": "n4",
            "source_span": {
              "start": 28,
              "end": 37
            },
            "grammatical_role": "object",
            "dep_label": "dobj",
            "head_id": "n7"
          }
        ],
        "node_id": "n4",
        "parent_id": "n1",
        "source_span": {
          "start": 4,
          "end": 37
        },
        "grammatical_role": "predicate"
      },
      {
        "type": "Phrase",
        "content": "her instincts",
        "tense": "null",
        "aspect": "simple",
        "mood": "indicative",
        "voice": "active",
        "finiteness": "non-finite",
        "linguistic_notes": [
          "Sentence is a noun phrase used to express her instincts."
        ],
        "notes": [
          {
            "text": "Sentence is a noun phrase used to express her instincts.",
            "kind": "syntactic",
            "confidence": 0.85,
            "source": "model"
          }
        ],
        "quality_flags": [
          "note_generated",
          "model_used"
        ],
        "rejected_candidates": [
          "Verb-centred phrase expressing what happens to or about the subject."
        ],
        "rejected_candidate_stats": [
          {
            "text": "Verb-centred phrase expressing what happens to or about the subject.",
            "count": 2,
            "reasons": [
              "MODEL_OUTPUT_LOW_QUALITY"
            ]
          }
        ],
        "reason_codes": [
          "MODEL_NOTE_ACCEPTED"
        ],
        "schema_version": "v2",
        "part_of_speech": "noun phrase",
        "linguistic_elements": [
          {
            "type": "Word",
            "content": "her",
            "tense": "null",
            "aspect": "null",
            "mood": "null",
            "voice": "null",
            "finiteness": "null",
            "linguistic_notes": [
              "'her' is a pronoun used to refer to an entity without repeating a full noun phrase."
            ],
            "notes": [
              {
                "text": "'her' is a pronoun used to refer to an entity without repeating a full noun phrase.",
                "kind": "syntactic",
                "confidence": 0.65,
                "source": "fallback"
              }
            ],
            "quality_flags": [
              "fallback_used"
            ],
            "rejected_candidates": [
              "Sentence is a nod to her instincts."
            ],
            "rejected_candidate_stats": [
              {
                "text": "Sentence is a nod to her instincts.",
                "count": 1,
                "reasons": [
                  "MODEL_NOTE_UNSUITABLE"
                ]
              }
            ],
            "reason_codes": [
              "MODEL_NOTE_UNSUITABLE",
              "FALLBACK_NOTE_ACCEPTED"
            ],
            "schema_version": "v2",
            "part_of_speech": "pronoun",
            "linguistic_elements": [],
            "features": {
              "number": "sing",
              "person": "3",
              "case": "null",
              "degree": "null",
              "definiteness": "null",
              "verb_form": "null",
              "gender": "fem",
              "tense_feature": "null"
            },
            "node_id": "n11",
            "parent_id": "n10",
            "source_span": {
              "start": 24,
              "end": 27
            },
            "grammatical_role": "other",
            "dep_label": "poss",
            "head_id": "n12"
          },
          {
            "type": "Word",
            "content": "instincts",
            "tense": "null",
            "aspect": "null",
            "mood": "null",
            "voice": "null",
            "finiteness": "null",
            "linguistic_notes": [
              "'instincts' is a noun that names an entity, concept, or object in context."
            ],
            "notes": [
              {
                "text": "'instincts' is a noun that names an entity, concept, or object in context.",
                "kind": "syntactic",
                "confidence": 0.65,
                "source": "fallback"
              }
            ],
            "quality_flags": [
              "fallback_used"
            ],
            "rejected_candidates": [
              "Sentence is a noun used as the subject of the clause."
            ],
            "rejected_candidate_stats": [
              {
                "text": "Sentence is a noun used as the subject of the clause.",
                "count": 1,
                "reasons": [
                  "MODEL_NOTE_UNSUITABLE"
                ]
              }
            ],
            "reason_codes": [
              "MODEL_NOTE_UNSUITABLE",
              "FALLBACK_NOTE_ACCEPTED"
            ],
            "schema_version": "v2",
            "part_of_speech": "noun",
            "linguistic_elements": [],
            "features": {
              "number": "plur",
              "person": "null",
              "case": "null",
              "degree": "null",
              "definiteness": "null",
              "verb_form": "null",
              "gender": "null",
              "tense_feature": "null"
            },
            "node_id": "n12",
            "parent_id": "n10",
            "source_span": {
              "start": 28,
              "end": 37
            },
            "grammatical_role": "object",
            "dep_label": "dobj",
            "head_id": null
          }
        ],
        "node_id": "n10",
        "parent_id": "n1",
        "source_span": {
          "start": 24,
          "end": 37
        },
        "grammatical_role": "object"
      },
      {
        "type": "Phrase",
        "content": "before making the decision",
        "tense": "null",
        "aspect": "simple",
        "mood": "indicative",
        "voice": "active",
        "finiteness": "non-finite",
        "linguistic_notes": [
          "The phrase 'before making the decision' is a prepositional phrase introducing relational context such as location, time, or semantic linkage."
        ],
        "notes": [
          {
            "text": "The phrase 'before making the decision' is a prepositional phrase introducing relational context such as location, time, or semantic linkage.",
            "kind": "syntactic",
            "confidence": 0.65,
            "source": "fallback"
          }
        ],
        "quality_flags": [
          "fallback_used"
        ],
        "rejected_candidates": [
          "Sentence is a node used as the subject of the clause.",
          "Verb-centred phrase expressing what happens to or about the subject.",
          "Sentence is a nod used as the subject of the clause."
        ],
        "rejected_candidate_stats": [
          {
            "text": "Sentence is a node used as the subject of the clause.",
            "count": 1,
            "reasons": [
              "MODEL_OUTPUT_LOW_QUALITY"
            ]
          },
          {
            "text": "Verb-centred phrase expressing what happens to or about the subject.",
            "count": 1,
            "reasons": [
              "MODEL_OUTPUT_LOW_QUALITY"
            ]
          },
          {
            "text": "Sentence is a nod used as the subject of the clause.",
            "count": 1,
            "reasons": [
              "MODEL_NOTE_UNSUITABLE"
            ]
          }
        ],
        "reason_codes": [
          "MODEL_NOTE_UNSUITABLE",
          "FALLBACK_NOTE_ACCEPTED"
        ],
        "schema_version": "v2",
        "part_of_speech": "prepositional phrase",
        "linguistic_elements": [
          {
            "type": "Word",
            "content": "before",
            "tense": "null",
            "aspect": "null",
            "mood": "null",
            "voice": "null",
            "finiteness": "null",
            "linguistic_notes": [
              "'before' is a preposition that links a noun phrase to another sentence element."
            ],
            "notes": [
              {
                "text": "'before' is a preposition that links a noun phrase to another sentence element.",
                "kind": "syntactic",
                "confidence": 0.65,
                "source": "fallback"
              }
            ],
            "quality_flags": [
              "fallback_used"
            ],
            "rejected_candidates": [
              "Sentence is a nod to the subject of the clause."
            ],
            "rejected_candidate_stats": [
              {
                "text": "Sentence is a nod to the subject of the clause.",
                "count": 1,
                "reasons": [
                  "MODEL_NOTE_UNSUITABLE"
                ]
              }
            ],
            "reason_codes": [
              "MODEL_NOTE_UNSUITABLE",
              "FALLBACK_NOTE_ACCEPTED"
            ],
            "schema_version": "v2",
            "part_of_speech": "preposition",
            "linguistic_elements": [],
            "features": {
              "number": "null",
              "person": "null",
              "case": "null",
              "degree": "null",
              "definiteness": "null",
              "verb_form": "null",
              "gender": "null",
              "tense_feature": "null"
            },
            "node_id": "n14",
            "parent_id": "n13",
            "source_span": {
              "start": 38,
              "end": 44
            },
            "grammatical_role": "linker",
            "dep_label": "prep",
            "head_id": null
          },
          {
            "type": "Word",
            "content": "making",
            "tense": "present participle",
            "aspect": "progressive",
            "mood": "null",
            "voice": "active",
            "finiteness": "non-finite",
            "linguistic_notes": [
              "'making' is a present participle that can mark progressive aspect or modifier function."
            ],
            "notes": [
              {
                "text": "'making' is a present participle that can mark progressive aspect or modifier function.",
                "kind": "morphological",
                "confidence": 0.65,
                "source": "fallback"
              }
            ],
            "quality_flags": [
              "fallback_used"
            ],
            "rejected_candidates": [
              "Sentence is a nod to a conversation."
            ],
            "rejected_candidate_stats": [
              {
                "text": "Sentence is a nod to a conversation.",
                "count": 1,
                "reasons": [
                  "MODEL_NOTE_UNSUITABLE"
                ]
              }
            ],
            "reason_codes": [
              "MODEL_NOTE_UNSUITABLE",
              "FALLBACK_NOTE_ACCEPTED"
            ],
            "schema_version": "v2",
            "part_of_speech": "verb",
            "linguistic_elements": [],
            "features": {
              "number": "null",
              "person": "null",
              "case": "null",
              "degree": "null",
              "definiteness": "null",
              "verb_form": "part",
              "gender": "null",
              "tense_feature": "pres"
            },
            "node_id": "n15",
            "parent_id": "n13",
            "source_span": {
              "start": 45,
              "end": 51
            },
            "grammatical_role": "other",
            "dep_label": "pcomp",
            "head_id": "n14"
          },
          {
            "type": "Word",
            "content": "the",
            "tense": "null",
            "aspect": "null",
            "mood": "null",
            "voice": "null",
            "finiteness": "null",
            "linguistic_notes": [
              "'the' is the definite article, signaling a specific or identifiable noun reference."
            ],
            "notes": [
              {
                "text": "'the' is the definite article, signaling a specific or identifiable noun reference.",
                "kind": "semantic",
                "confidence": 0.65,
                "source": "fallback"
              }
            ],
            "quality_flags": [
              "fallback_used"
            ],
            "rejected_candidates": [
              "Sentence is a nod to the subject of the clause."
            ],
            "rejected_candidate_stats": [
              {
                "text": "Sentence is a nod to the subject of the clause.",
                "count": 1,
                "reasons": [
                  "MODEL_NOTE_UNSUITABLE"
                ]
              }
            ],
            "reason_codes": [
              "MODEL_NOTE_UNSUITABLE",
              "FALLBACK_NOTE_ACCEPTED"
            ],
            "schema_version": "v2",
            "part_of_speech": "article",
            "linguistic_elements": [],
            "features": {
              "number": "null",
              "person": "null",
              "case": "null",
              "degree": "null",
              "definiteness": "def",
              "verb_form": "null",
              "gender": "null",
              "tense_feature": "null"
            },
            "node_id": "n16",
            "parent_id": "n13",
            "source_span": {
              "start": 52,
              "end": 55
            },
            "grammatical_role": "determiner",
            "dep_label": "det",
            "head_id": "n17"
          },
          {
            "type": "Word",
            "content": "decision",
            "tense": "null",
            "aspect": "null",
            "mood": "null",
            "voice": "null",
            "finiteness": "null",
            "linguistic_notes": [
              "'decision' is a noun that names an entity, concept, or object in context."
            ],
            "notes": [
              {
                "text": "'decision' is a noun that names an entity, concept, or object in context.",
                "kind": "syntactic",
                "confidence": 0.65,
                "source": "fallback"
              }
            ],
            "quality_flags": [
              "fallback_used"
            ],
            "rejected_candidates": [
              "Sentence is a noun used as the subject of the clause."
            ],
            "rejected_candidate_stats": [
              {
                "text": "Sentence is a noun used as the subject of the clause.",
                "count": 1,
                "reasons": [
                  "MODEL_NOTE_UNSUITABLE"
                ]
              }
            ],
            "reason_codes": [
              "MODEL_NOTE_UNSUITABLE",
              "FALLBACK_NOTE_ACCEPTED"
            ],
            "schema_version": "v2",
            "part_of_speech": "noun",
            "linguistic_elements": [],
            "features": {
              "number": "sing",
              "person": "null",
              "case": "null",
              "degree": "null",
              "definiteness": "null",
              "verb_form": "null",
              "gender": "null",
              "tense_feature": "null"
            },
            "node_id": "n17",
            "parent_id": "n13",
            "source_span": {
              "start": 56,
              "end": 64
            },
            "grammatical_role": "object",
            "dep_label": "dobj",
            "head_id": "n15"
          }
        ],
        "node_id": "n13",
        "parent_id": "n1",
        "source_span": {
          "start": 38,
          "end": 64
        },
        "grammatical_role": "modifier"
      }
    ],
    "node_id": "n1",
    "parent_id": null,
    "source_span": {
      "start": 0,
      "end": 65
    },
    "grammatical_role": "clause"
  }
}```
