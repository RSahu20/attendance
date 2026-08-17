import type { IngestionJob, UploadResult } from "../types";

interface Props {
  upload: UploadResult | null;
  job: IngestionJob | null;
}

export function ProcessingPanel({ upload, job }: Props) {
  const failed = job?.status === "failed";
  const complete = job?.status === "completed";
  const reviewRequired = job?.status === "review_required";
  return (
    <section className="panel" aria-labelledby="processing-title">
      <div className="section-heading">
        <div>
          <p className="step">2 · Processing</p>
          <h2 id="processing-title">Ingestion status</h2>
        </div>
        <span className={`badge ${failed ? "badge--error" : complete ? "badge--ready" : "badge--neutral"}`}>
          {job?.status ?? (upload ? "checking" : "waiting")}
        </span>
      </div>
      {!upload && <p className="empty">Upload a file to see normalization progress.</p>}
      {upload && (
        <>
          <dl className="metrics">
            <div><dt>Stage</dt><dd>{job?.current_stage ?? upload.status}</dd></div>
            <div><dt>Extracted units</dt><dd>{job?.extracted_unit_count ?? "—"}</dd></div>
            <div><dt>Normalized records</dt><dd>{job?.normalized_record_count ?? "—"}</dd></div>
            <div><dt>Review required</dt><dd>{job?.review_required_count ?? "—"}</dd></div>
          </dl>
          <p className="identifier"><span>Job ID</span>{upload.job_id}</p>
          {complete && <div className="message message--success">Processing completed successfully.</div>}
          {reviewRequired && (
            <div className="message message--warning" role="status">
              Processing finished, but human review is required. Check the reason below.
            </div>
          )}
          {failed && <div className="message message--error" role="alert">Processing failed. Review the safe errors below.</div>}
          {!!job?.errors.length && (
            <ul className="errors">
              {job.errors.map((error, index) => <li key={index}>{String(error.message ?? error.code ?? "Processing error")}</li>)}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
