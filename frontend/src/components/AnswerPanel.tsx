import type { AnswerResult, Citation } from "../types";

function values(record: Record<string, string | string[]>): string {
  return Object.values(record).flat().join(", ");
}

function sourceName(citation: Citation): string {
  const locator = citation.source_locator;
  return String(locator.source_file ?? locator.filename ?? locator.file ?? "Authorized source");
}

export function AnswerPanel({ result }: { result: AnswerResult | null }) {
  if (!result) return null;
  const unavailable = result.status === "unavailable";
  return (
    <section className={`panel answer ${unavailable ? "answer--unavailable" : ""}`} aria-labelledby="answer-title">
      <div className="section-heading">
        <div><p className="step">4 · Answer</p><h2 id="answer-title">{unavailable ? "Evidence unavailable" : "Grounded answer"}</h2></div>
        <span className={`badge ${unavailable ? "badge--error" : "badge--ready"}`}>{result.status}</span>
      </div>
      <p className="answer-text">{result.answer}</p>
      {result.unavailable_reason && <p className="reason">Reason: {result.unavailable_reason}</p>}
      <div className="confidence">
        <strong>Confidence: {result.confidence.band.toUpperCase()}</strong>
        <span>{result.confidence.score.toFixed(2)}</span>
        <span>Mode: {result.retrieval_mode.toUpperCase()}</span>
      </div>
      <dl className="context-grid">
        <div><dt>Tenant</dt><dd>{values(result.tenant_context)}</dd></div>
        <div><dt>Entity</dt><dd>{values(result.entity_context)}</dd></div>
        <div><dt>Role</dt><dd>{values(result.role_context)}</dd></div>
      </dl>
      <div className="request-meta"><span>Request ID: {result.request_id}</span><span>Audit ID: {result.audit_id}</span></div>
      <div className="sources">
        <h3>Validated sources</h3>
        {!result.citations.length && <p className="empty">No citations returned for this answer mode.</p>}
        {result.citations.map((citation) => (
          <article className="citation" key={citation.evidence_id}>
            <div><span className="citation-id">{citation.evidence_id}</span><strong>{sourceName(citation)}</strong></div>
            <p>{citation.claim}</p>
            <dl>
              {Object.entries(citation.source_locator).map(([key, value]) => (
                <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>
              ))}
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}
