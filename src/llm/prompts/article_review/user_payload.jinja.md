Review this FX/finance article draft for human editorial workflow.

Return one AIReview JSON object with this shape:
{
  "publish_readiness": "ready | needs_edit | reject",
  "scores": {
    "grounding": 0,
    "depth": 0,
    "readability": 0,
    "headline_quality": 0,
    "financial_safety": 0,
    "source_usefulness": 0
  },
  "issues": [
    {
      "issue_type": "grounding | depth | readability | headline_quality | financial_safety | source_usefulness | overstatement | other",
      "severity": "low | medium | high",
      "location": "title | summary | body | faq | sources_used | article",
      "description": "specific issue",
      "suggested_fix": "specific editor-facing fix"
    }
  ],
  "unsupported_claims": [],
  "overstatements": [],
  "missing_context": [],
  "rewrite_suggestions": [],
  "recommended_editor_action": "specific action for the editor"
}

Hard rules:
- If there are unsupported claims, publish_readiness must not be "ready".
- If there is financial advice or guaranteed-outcome language, publish_readiness must be "needs_edit" or "reject".
- If source_quality_report recommends write_brief_only, penalize depth unless the article is clearly a market brief.
- If source_quality_report recommends skip_or_manual_review, publish_readiness must not be "ready".
- Reviewer must not rewrite the article body.

article:
{{ article | tojson }}

editorial_brief:
{{ editorial_brief | tojson }}

source_bundle:
{{ source_bundle | tojson }}

source_quality_report:
{{ source_quality_report | tojson }}

validation:
{{ validation | tojson }}
