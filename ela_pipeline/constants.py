"""Shared constants for the ELA pipeline."""

NODE_TYPES = {"Sentence", "Phrase", "Word"}

REQUIRED_NODE_FIELDS = {
    "type",
    "content",
    "tense",
    "linguistic_notes",
    "part_of_speech",
    "linguistic_elements",
}

FUTURE_MODALS = {"will", "shall"}
NEGATIONS = {"not", "n't", "never"}
BE_FORMS = {"be", "am", "is", "are", "was", "were", "been", "being"}
HAVE_FORMS = {"have", "has", "had"}
