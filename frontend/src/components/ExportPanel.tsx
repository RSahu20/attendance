import type { ExportFormat } from "../types";

interface Props {
  busy: ExportFormat | null;
  message: string | null;
  error: string | null;
  onExport: (format: ExportFormat) => Promise<void>;
}

export function ExportPanel({ busy, message, error, onExport }: Props) {
  return (
    <section className="panel" aria-labelledby="export-title">
      <p className="step">5 · Export</p>
      <h2 id="export-title">Download authorized records</h2>
      <p className="help">The backend revalidates access and creates each artifact.</p>
      <div className="export-actions">
        {(["json", "xlsx", "pdf"] as ExportFormat[]).map((format) => (
          <button className="button button--secondary" disabled={busy !== null} key={format} onClick={() => void onExport(format)} type="button">
            {busy === format ? "Preparing…" : `Export ${format.toUpperCase()}`}
          </button>
        ))}
      </div>
      {message && <div className="message message--success" role="status">{message}</div>}
      {error && <div className="message message--error" role="alert">{error}</div>}
    </section>
  );
}
