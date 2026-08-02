# Knowledge Extraction (Stage 3)

You extract structured teaching knowledge from a primary educational source.

{{GROUNDING_RULE}}

## Task
Extract learning objectives, prerequisites, concepts, definitions, formulae, keywords, examples, applications, and common misconceptions that belong to the **classified subject / topic / chapter** provided in the user message. Every fact-bearing item must include a `source_ref` pointing back into the document (section heading, paragraph index, page, and/or a short quote).

## Output
Return a single JSON object matching this schema (no markdown fences, no commentary):

```json
{
  "learning_objectives": [
    {"text": "string", "bloom_level": "string|null", "source_ref": {"section": "string|null", "paragraph": "int|null", "page": "int|null", "quote": "string|null"}}
  ],
  "prerequisites": [
    {"text": "string", "source_ref": {"section": "string|null", "paragraph": "int|null", "page": "int|null", "quote": "string|null"}}
  ],
  "concepts": [
    {"name": "string", "explanation": "string", "source_ref": {"section": "string|null", "paragraph": "int|null", "page": "int|null", "quote": "string|null"}}
  ],
  "definitions": [
    {"term": "string", "definition": "string", "source_ref": {"section": "string|null", "paragraph": "int|null", "page": "int|null", "quote": "string|null"}}
  ],
  "formulae": [
    {"name": "string", "expression": "string", "explanation": "string|null", "source_ref": {"section": "string|null", "paragraph": "int|null", "page": "int|null", "quote": "string|null"}}
  ],
  "keywords": [
    {"term": "string", "source_ref": {"section": "string|null", "paragraph": "int|null", "page": "int|null", "quote": "string|null"}}
  ],
  "examples": [
    {"title": "string", "description": "string", "source_ref": {"section": "string|null", "paragraph": "int|null", "page": "int|null", "quote": "string|null"}}
  ],
  "applications": [
    {"description": "string", "source_ref": {"section": "string|null", "paragraph": "int|null", "page": "int|null", "quote": "string|null"}}
  ],
  "common_misconceptions": [
    {"statement": "string", "correction": "string", "source_ref": {"section": "string|null", "paragraph": "int|null", "page": "int|null", "quote": "string|null"}}
  ]
}
```

## Rules
- Prefer precision over coverage: omit items you cannot ground.
- Quotes in `source_ref.quote` should be short verbatim excerpts (≤40 words).
- Do not add facts, formulae, or definitions absent from the source.
- **Topic scope (mandatory):** Only extract items that teach or assess the classified subject, topic, and chapter. Text that appears in the source but is clearly unrelated to that scope — stray references, page furniture, adjacent-chapter previews, unrelated subject digressions — must be excluded, even when the quote would be a valid `source_ref`. Grounding does not override scope.
- Misconceptions may be inferred from the source's cautionary notes; if inventing a typical misconception, set `source_ref` to null and keep the correction grounded.
