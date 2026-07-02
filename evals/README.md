# Promptfoo Eval Skeleton

This directory contains the first Promptfoo regression-eval skeleton for the FX content pipeline.

It is intentionally opt-in:

```bash
ENABLE_PROMPTFOO_EVALS=1 promptfoo eval -c evals/promptfoo.yaml
```

Normal development and pytest do not run Promptfoo or call live LLMs.

Current scope:

- Validate the planned eval contract.
- Store early USD/IDR golden samples.
- Keep assertions focused on structure, grounding, financial safety, headline risk, and helpful-content signals.

Before using this in CI, expand `evals/samples/usd_idr/` to at least 20 reviewed samples and decide which provider/model should grade rubric assertions.
