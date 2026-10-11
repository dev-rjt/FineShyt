# Grounded LLM explanation engine

This implements the explanation layer in the Lloyds PS1 proposal: customer
insights and bank-staff/relationship-manager explanations from the final v1
opportunity contract. It connects to local Ollama without an API key or to
Ollama Cloud with bearer authentication. Template mode works without Ollama.
Python 3.11+ is supported; tests use 3.12.

## Run without a model

From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-llm.txt
python -m src.llm --records tests/fixtures/eligible_ev.json \
  --output data/reports/llm/eligible_ev.json
python -m src.llm.evaluate --output data/reports/llm/template_evaluation.json
```

Outputs are full copies of the input opportunity records with only
`explanation` replaced. Existing files are never overwritten. The runner accepts
a single full JSON object, an array of full objects, or JSONL. PDF section
fragments such as `ineligible_ev.json` must first be combined with a complete
upstream record. The evaluation runner does that explicitly for synthetic tests.

## Run with local Ollama

Install [Ollama](https://ollama.com/download) and start its local service.
`qwen2.5:3b` is an initial candidate for a laptop with about 8 GB RAM and an RTX
4060: its quantized weights are approximately 1.9 GB according to the
[model listing](https://ollama.com/library/qwen2.5:3b). Runtime memory exceeds
the weight size; measure performance on your machine. No model is downloaded by
this package. Use another installed model by changing `OLLAMA_MODEL`.

```bash
ollama pull qwen2.5:3b
ollama list
# Run this in another terminal if the desktop app is not already serving:
ollama serve
```

In the project terminal with the Python environment activated:

```bash
export OLLAMA_MODEL=qwen2.5:3b
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export OLLAMA_TIMEOUT_SECONDS=90
python -m src.llm --provider ollama --require-llm \
  --records tests/fixtures/eligible_ev.json \
  --output data/reports/llm/ollama_ev.json
python -m src.llm.evaluate --provider ollama \
  --output data/reports/llm/ollama_evaluation.json
```

`--require-llm` exits nonzero if any visible explanation uses a template, while
still writing the safe result for inspection. Without that option, verified
fallbacks are successful delivery. Summary output contains counts, not customer
records. Missing `OLLAMA_MODEL` is a configuration error. A configured model that
is unavailable, times out, or returns invalid output triggers a fallback.

Loopback HTTP and the official `https://ollama.com` cloud origin are supported.
Set `OLLAMA_API_KEY` when using the cloud origin; it is sent only in the bearer
authorization header. `OLLAMA_ALLOW_LAN=true` explicitly enables a custom
private endpoint. The transport bypasses environment proxies for loopback,
disallows redirects, and uses a single bounded request. Requests use `/api/chat`,
`stream: false`, a JSON Schema `format`,
temperature zero, seed 2026 and an 8192-token context. The schema integration
follows [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
and the [chat API](https://docs.ollama.com/api/chat).

For Ollama Cloud:

```bash
export OLLAMA_API_KEY=your_private_key
export OLLAMA_BASE_URL=https://ollama.com
export OLLAMA_MODEL=gemma4:31b
export OLLAMA_ALLOW_LAN=false
```

## Grounding and audience handling

1. Validate the complete input with the Responsible AI contract checks. Product
   ID/name/code must agree; unreviewed primary impact units fail before a call.
2. Build a small catalog of reviewed sentences from approved structured fields.
   Customer IDs, request IDs, demographics, raw transactions, arbitrary labels,
   free-text evidence, rule messages, old explanations and audit logs are absent
   from the model prompt. Numeric evidence uses reviewed metric/unit combinations.
3. Ollama selects sentence variants and ordering for each audience in a strict
   JSON explanation plan. Every supplied fact card is mandatory exactly once.
4. The verifier checks keys, IDs, variants, completeness and audience scope.
   Unsupported prose, invented fields/numbers and missing caveats are rejected.
5. Render only the selected approved sentences. Verify the deterministic template
   through the same path after any provider or verification failure.
6. Validate the final contract and compare every field outside `explanation`
   with the original snapshot.

The customer message contains relevance, confidence, estimated impact when
available, method, assumptions, an approved action and the data cutoff. Staff
also receive model scores, evidence, blocked-rule identifiers, factor provenance,
missing-data notes and human-review needs. Low confidence is flagged using the
upstream confidence band; the engine does not create a threshold or new score.
Supporting emissions, energy, paper and digital metrics retain their own units.

`headline` and `customer_message` are null unless the existing customer visibility
flag is true, eligibility is `ELIGIBLE`, and the decision is `RECOMMEND`.
`manager_message` is null when manager visibility is false. Blocked and review
cases can produce internal staff explanations without creating a customer offer.
The engine does not change those flags or compute decisions, carbon or rankings.

Generated model plans produce `VERIFIED`. Checked templates produce
`FALLBACK_USED`; deliberate offline mode is also a template fallback. With both
audiences hidden the status is `NOT_GENERATED` and no provider is called.
`verification.passed` describes the final delivered text. Rejected candidate
diagnostics in `unsupported_claims` are safe codes, never raw model output.

The wording is constrained to reviewed variants. This limits stylistic freedom
but makes factual verification deterministic. Unknown reason/rule/method codes
get an explicit generic description with identifiers preserved for staff; their
meaning is not guessed. New product actions and richer wording need reviewed
vocabulary updates in `src/llm/facts.py`. Unknown actions use a generic next step.

Grounding proves consistency with the selected structured facts. It does not
prove those facts are correct, validate emissions-factor sources, establish
financial eligibility, or certify security/fairness. Only approved synthetic
hackathon records belong in this prototype. The LLM engine is an explanation
component; it does not expose a general chat interface or execute agent tools.

## Integration API

```python
from copy import deepcopy
from src.llm import ExplanationEngine, OllamaProvider, component_versions
from responsible_ai.audit_log import append_audit

# `record` is a complete opportunity from the integration owner.
# The pipeline owner sets metadata before taking the explanation boundary snapshot.
prepared = deepcopy(record)
prepared["audit"]["component_versions"].update(component_versions())
engine = ExplanationEngine(OllamaProvider.from_env())
result = engine.generate(prepared)
append_audit(result)

# Customer/business API handlers enforce these flags at their own boundary too.
customer_text = result["explanation"]["customer_message"]
staff_text = result["explanation"]["manager_message"]
```

Reuse an engine instance to enable a bounded memory cache of accepted model
plans. The cache key includes the actual explanation facts, prompt/schema,
provider/model/endpoint and verifier versions. Cached plans are checked again;
failed candidates are not cached. The cache stores no raw records and never
writes to disk. `cache_size=0` disables it. Cross-process caching is not included.

The engine preserves audit metadata. The pipeline owner must stamp the versions
returned by `component_versions()` before generation. CLI input files must already
carry correct pipeline metadata; the CLI does not rewrite upstream audit fields.

This branch derives from `Harshik-responsible-ai` and depends on that package
and `contracts/opportunity_v1.schema.json`. The remote `feat/backend-setup`
branch currently uses an older flat API format (`gate`, `insight`, `data_as_of`).
It needs an explicitly agreed adapter or a migration to the final nested contract
before wiring this engine into its endpoints. No old API fields are silently
mapped to financial eligibility. The final schema currently documents EV
calculation-input keys only; other product inputs need team agreement. The engine
can explain all four product codes, including unavailable-impact cases.

## Tests and evaluation

```bash
python -m pip install -r requirements-rai.txt
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider \
  tests/responsible_ai tests/llm
```

The synthetic evaluation has eight cases: eligible EV, blocked EV despite high
propensity, missing data, calculation error, human review, and an unavailable
impact example for each other product. Tests additionally cover invalid model
responses, invented prose, audience mixing, omissions, unsupported product
mapping, null scores, zero/negative impact, low confidence, prompt minimization,
transport errors, cache invalidation and output-file protection.

See [synthetic template examples](examples/llm/template_examples.json) for both
audiences. That file contains explanation fragments for review, not complete
opportunity records for the CLI input.

Evaluation reports distinguish model-plan acceptance from fallback delivery and
check final contract validity, visibility, verification and timestamps. Template
and mocked-provider results do not measure live model quality. Before submission,
run the installed model on team-authored validation records, compare readability
and completeness with templates, review factual claims, record latency and the
exact model digest (`ollama list`), and publish actual acceptance/fallback rates.
Keep the real test set separate. No live model metrics are claimed here.

## Inputs still needed from teammates

- Complete final-contract records for all four products and edge cases, with
  correct versions, visibility and doctored IDs.
- The canonical reason-code and action vocabulary with approved wording.
- Agreement on the final contract versus the backend's older API shape.
- Installed Ollama model/digest and measured runtime performance on the target
  laptop, plus human-reviewed explanation evaluation cases.
