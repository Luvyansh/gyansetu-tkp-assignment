# Learning Gap Analysis (Stage 8)

You identify likely learning gaps and misconceptions for this unit, with diagnostics and remediation.

## Task
Using extracted knowledge (especially `common_misconceptions`, prerequisites, and dense concepts), produce a gap analysis teachers can use for formative diagnosis.

## Output
Return a single JSON object (no markdown fences, no commentary):

```json
{
  "gaps": [
    {
      "misconception": "string",
      "diagnostic_question": "string — reveals whether the misconception is present",
      "severity": "low | medium | high",
      "remedial_actions": ["string"],
      "related_concepts": ["string"]
    }
  ],
  "summary": "string — brief overview for the teacher"
}
```

## Rules
- Prefer misconceptions already listed in extracted knowledge; you may add high-likelihood gaps typical for the grade/topic when clearly labeled by severity.
- Remedial actions should be practical classroom strategies (reteach, analogy, worked example, peer explanation).
- Diagnostic questions should be answerable in under 2 minutes.
- Aim for 3–8 gaps unless the unit is very narrow.
- Do not contradict source corrections when present.
