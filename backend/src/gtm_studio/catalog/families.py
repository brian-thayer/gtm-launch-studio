"""The output families the backend knows how to draft and render."""

# Families are code (output schemas, S34), not taxonomy.
KNOWN_FAMILIES: frozenset[str] = frozenset(
    {"generic_doc", "classification", "battlecard", "email_set", "deck", "launch_video"}
)
