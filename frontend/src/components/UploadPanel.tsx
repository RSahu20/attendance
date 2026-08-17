import { useState, type FormEvent } from "react";

import type { Classification, Grant, WorkContext } from "../types";

interface Props {
  grants: Grant[];
  busy: boolean;
  error: string | null;
  onUpload: (file: File, context: WorkContext) => Promise<void>;
  onContextChange: (context: WorkContext) => void;
}

const classificationNames = ["Public", "Internal", "Confidential", "Restricted"];

export function UploadPanel({ grants, busy, error, onUpload, onContextChange }: Props) {
  const scopedGrants = grants.filter((grant) => grant.entity_id);
  const first = scopedGrants[0];
  const [file, setFile] = useState<File | null>(null);
  const [entityId, setEntityId] = useState(first?.entity_id ?? "");
  const [module, setModule] = useState(first?.module ?? "attendance");
  const [classification, setClassification] = useState<Classification>(
    Math.min(1, first?.classification_ceiling ?? 0) as Classification,
  );
  const [sampleError, setSampleError] = useState<string | null>(null);

  function context(next: Partial<WorkContext> = {}): WorkContext {
    return { entityId, module, classification, ...next };
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (file) await onUpload(file, context());
  }

  async function selectDemoFile(): Promise<void> {
    setSampleError(null);
    try {
      const response = await fetch("/attendance-demo.csv");
      if (!response.ok) throw new Error();
      const blob = await response.blob();
      setFile(new File([blob], "attendance-demo.csv", { type: "text/csv" }));
    } catch {
      setSampleError("The built-in demo file could not be loaded. Refresh the page and try again.");
    }
  }

  return (
    <section className="panel" aria-labelledby="upload-title">
      <div className="section-heading">
        <div>
          <p className="step">1 · Upload</p>
          <h2 id="upload-title">Attendance evidence</h2>
        </div>
        <span className="badge badge--ready">Authorized</span>
      </div>
      <form className="form-grid" onSubmit={(event) => void submit(event)}>
        <label className="file-picker field--wide">
          <span>{file ? "Change file" : "Choose attendance file"}</span>
          <input
            accept=".csv,.xlsx,.docx,.pdf,.png,.jpg,.jpeg,.tif,.tiff"
            aria-label="Attendance file"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            type="file"
          />
        </label>
        <button
          className="button button--secondary field--wide"
          onClick={() => void selectDemoFile()}
          type="button"
        >
          Use built-in demo CSV
        </button>
        {file && (
          <div className="file-summary field--wide" aria-live="polite">
            <strong>{file.name}</strong>
            <span>{file.type || "Unknown file type"} · {(file.size / 1024).toFixed(1)} KB</span>
          </div>
        )}
        <label className="field">
          <span>Entity</span>
          <select
            aria-label="Entity"
            onChange={(event) => {
              setEntityId(event.target.value);
              onContextChange(context({ entityId: event.target.value }));
            }}
            value={entityId}
          >
            {scopedGrants.map((grant) => (
              <option key={`${grant.role_id}-${grant.entity_id}`} value={grant.entity_id ?? ""}>
                {grant.entity_id}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Module</span>
          <input
            aria-label="Module"
            onChange={(event) => {
              setModule(event.target.value);
              onContextChange(context({ module: event.target.value }));
            }}
            value={module}
          />
        </label>
        <label className="field">
          <span>Classification</span>
          <select
            aria-label="Classification"
            onChange={(event) => {
              const value = Number(event.target.value) as Classification;
              setClassification(value);
              onContextChange(context({ classification: value }));
            }}
            value={classification}
          >
            {classificationNames.map((name, value) => (
              <option disabled={value > (first?.classification_ceiling ?? 0)} key={name} value={value}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <button className="button" disabled={!file || busy} type="submit">
          {busy ? "Uploading…" : "Upload and process"}
        </button>
      </form>
      {error && <div className="message message--error" role="alert">{error}</div>}
      {sampleError && <div className="message message--error" role="alert">{sampleError}</div>}
    </section>
  );
}
