# Grounded Answer Generation

## Implemented flow

```text
authorized query request
  -> structured/document/hybrid retrieval
  -> transaction-local authorization context restored
  -> context rows revalidated against scope + current versions
  -> PII minimization and prompt-injection marking/redaction
  -> deterministic structured answer OR typed LLM provider output
  -> citation ID/source/support validation
  -> one bounded correction retry
  -> reproducible confidence score and threshold gate
  -> answered or controlled unavailable response
  -> sanitized append-only generation audit event
```

The LLM never receives database, retrieval, export, or authorization tools. It receives
only context that was already retrieved and independently revalidated for the caller's
product, tenant, entity, module, classification, and permissions.

## Provider contract

`LLMProvider` accepts a typed `LLMRequest` and must return a typed `ProviderOutput`.
`MockProvider` is the deterministic default and enables offline tests/demos.
`OpenAIProvider` uses the Responses API structured-output parser and is activated only
when `LLM_PROVIDER=openai` and `OPENAI_API_KEY` are configured. Provider output cannot
grant access or create a valid citation by itself.

## Context and injection handling

The context builder queries every candidate chunk again with explicit protected-scope
predicates and existing PostgreSQL RLS. Missing, stale, or mismatched chunks are dropped.
Email addresses and phone-like values are minimized before external-provider context.
Common instructions embedded in documents—such as requests to ignore earlier rules,
reveal a system prompt, or change tenant/scope—are marked and redacted as untrusted data.

## Citations and grounding

The application assigns opaque evidence IDs before generation. Validation requires that
each cited ID exists in this request's authorized context, has a source locator, and has
sufficient lexical support for its claim. The final answer must also overlap its cited
support. Invented or unsupported citations trigger one correction attempt; a second
failure returns `INVALID_CITATIONS` without exposing inaccessible evidence.

## Confidence

Confidence is a deterministic quality score, not a probability. It combines retrieval
coverage, keyword/vector agreement, extraction confidence, review status, injection
flags, structured-result availability, and citation validation. Bands are high (`>=.80`),
medium (`>=.55`), and low. `ANSWER_CONFIDENCE_THRESHOLD` defaults to `0.55`; results below
it return controlled `LOW_CONFIDENCE` rather than an answer.

## API response

`POST /api/v1/queries` returns the answer, tenant/entity/role context, validated
citations, confidence score/band, retrieval mode, request ID, generation audit ID,
status, and a safe unavailable reason when applicable.

## Phase boundary

Secure exports and the basic evaluator frontend are implemented separately. Stored query
history, advanced product UI, production identity-provider integration, and cloud
deployment remain deferred.
