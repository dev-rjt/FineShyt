"""One-way explanation engine: full validated record in, copied record out."""

from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
from threading import Lock

from .facts import build_catalog
from .contract_checks import validate_record
from .prompts import PROMPT_VERSION, VERIFIER_VERSION, messages, response_schema
from .verifier import render, template_plan, verify_plan


def component_versions():
    """The integration owner stamps these into audit before calling the engine."""
    return {"llm_prompt": PROMPT_VERSION, "llm_verifier": VERIFIER_VERSION}


class ExplanationEngine:
    def __init__(self, provider=None, *, cache_size=128):
        if not isinstance(cache_size, int) or isinstance(cache_size, bool) or cache_size < 0:
            raise ValueError("cache_size must be a nonnegative integer")
        self.provider = provider
        self.cache_size = cache_size
        self._cache = OrderedDict()
        self._cache_lock = Lock()

    def generate(self, record):
        """Change only explanation; visibility is enforced for both audiences.

        Invalid upstream records fail before any provider call. Provider errors or
        invalid model selections produce a checked deterministic fallback. Errors
        do not include raw model content. No predictions/ranking are calculated.
        """
        before = deepcopy(record)
        violations = validate_record(before)
        if violations:
            raise ValueError("Input contract invalid: " + "; ".join(violations))
        catalog = build_catalog(before)
        issues = []
        used_model = False
        provider_name, model = None, None
        if self.provider is not None and (catalog.customer or catalog.manager):
            provider_name, model = self.provider.name, self.provider.model
            schema = response_schema(catalog)
            prompt_messages = messages(catalog, schema)
            key = hashlib.sha256(json.dumps({"messages": prompt_messages, "schema": schema,
                                            "provider": provider_name, "model": model,
                                            "endpoint": getattr(self.provider, "base_url", None),
                                            "verifier": VERIFIER_VERSION, "prompt": PROMPT_VERSION},
                                           sort_keys=True, allow_nan=False).encode()).hexdigest()
            with self._cache_lock:
                plan = deepcopy(self._cache.get(key))
                if key in self._cache:
                    self._cache.move_to_end(key)
            if plan is None:
                try:
                    plan = self.provider.generate(deepcopy(prompt_messages), deepcopy(schema))
                except Exception:
                    # Arbitrary provider exceptions can contain confidential text.
                    issues = ["PROVIDER_FAILED"]
            if not issues:
                issues = verify_plan(plan, catalog)
            used_model = not issues
            if issues:
                with self._cache_lock:
                    self._cache.pop(key, None)
            if used_model and self.cache_size:
                with self._cache_lock:
                    self._cache[key] = deepcopy(plan)
                    self._cache.move_to_end(key)
                    while len(self._cache) > self.cache_size:
                        self._cache.popitem(last=False)
        if not used_model:
            plan = template_plan(catalog)
        # Templates and cached plans go through the same verifier as live output.
        rendered = render(plan, catalog)
        generated = any(value is not None for value in rendered.values())
        source_paths = sorted({path for card in (*catalog.customer, *catalog.manager) for path in card.sources})
        after = deepcopy(before)
        after["explanation"] = {
            "status": ("VERIFIED" if used_model else "FALLBACK_USED") if generated else "NOT_GENERATED",
            **rendered,
            "verification": {"passed": generated, "verified_fields": source_paths,
                             "unsupported_claims": issues, "fallback_used": generated and not used_model},
            "llm": {"provider": provider_name, "model": model, "prompt_version": PROMPT_VERSION},
        }
        violations = validate_record(after, before_llm=before)
        if violations:
            raise ValueError("Output contract invalid: " + "; ".join(violations))
        return after
