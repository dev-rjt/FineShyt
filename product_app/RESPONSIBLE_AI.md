# Responsible AI note

## Privacy and data

The demo contains only synthetic customers. No real personal or confidential
banking data is included. Customer access is scoped in the backend to the
customer ID in a signed session. The optional LLM receives only a constrained
opportunity payload; it never receives raw transactions, names or postcodes.

## Decision boundaries

- Propensity estimates take-up interest and never establishes eligibility.
- Illustrative product-rule gates override propensity when signals conflict.
- Authorised bank affordability, suitability and eligibility checks remain
  outside this prototype.
- The deterministic engine alone calculates impact; the language layer cannot
  calculate or change it.
- All impact is labelled as estimated, includes a horizon and method, and keeps
  emissions, energy, paper and digital adoption separate.

## Explainability and hallucination controls

Every recommendation exposes confidence, fixed reason codes, evidence wording,
data timestamp, method and assumptions. Generated text is checked so every
number must already exist in the structured payload. A failed check, network
failure or missing Ollama Cloud API key uses the deterministic template.

## Bias and model risk

The bank workspace includes descriptive recommendation-rate monitoring across
age, income and region. This does not certify fairness. Synthetic label rules
can encode their own assumptions, and subgroup differences require human review.
Held-out metrics, baseline comparisons, confidence intervals and limitations are
shown without claiming production accuracy.

## Human oversight and production work

A human remains accountable for customer contact and financial decisions.
Production deployment requires representative lawful data, DPIA/privacy review,
fairness assessment, accessibility and security testing, model validation,
approved emissions methodology, drift monitoring, incident management, an
enterprise identity provider and auditable customer-memory storage.
