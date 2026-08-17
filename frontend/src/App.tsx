import { useEffect, useState } from "react";

import {
  askQuestion,
  createAndDownloadExport,
  getAuthorizationContext,
  getIngestionJob,
  uploadDocument,
} from "./api";
import { AnswerPanel } from "./components/AnswerPanel";
import { AuthSetup } from "./components/AuthSetup";
import { ExportPanel } from "./components/ExportPanel";
import { ProcessingPanel } from "./components/ProcessingPanel";
import { QueryPanel } from "./components/QueryPanel";
import { UploadPanel } from "./components/UploadPanel";
import type {
  AnswerResult,
  ApiSession,
  AuthorizationContext,
  ExportFormat,
  IngestionJob,
  UploadResult,
  WorkContext,
} from "./types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The operation could not be completed.";
}

export default function App() {
  const [apiAvailable, setApiAvailable] = useState<boolean | null>(null);
  const [session, setSession] = useState<ApiSession | null>(null);
  const [authContext, setAuthContext] = useState<AuthorizationContext | null>(null);
  const [workContext, setWorkContext] = useState<WorkContext | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [job, setJob] = useState<IngestionJob | null>(null);
  const [querying, setQuerying] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<AnswerResult | null>(null);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBaseUrl}/health/live`, { signal: controller.signal })
      .then((response) => setApiAvailable(response.ok))
      .catch(() => setApiAvailable(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!session || !upload) return;
    const currentSession = session;
    const currentUpload = upload;
    let cancelled = false;
    let timer: number | undefined;
    async function poll(): Promise<void> {
      try {
        const next = await getIngestionJob(currentSession, currentUpload.job_id);
        if (cancelled) return;
        setJob(next);
        if (!["completed", "failed", "review_required", "cancelled"].includes(next.status)) {
          timer = window.setTimeout(() => void poll(), 1500);
        }
      } catch (error) {
        if (!cancelled) setUploadError(errorMessage(error));
      }
    }
    void poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [session, upload]);

  async function connect(nextSession: ApiSession): Promise<void> {
    setConnecting(true);
    setConnectionError(null);
    try {
      const resolved = await getAuthorizationContext(nextSession);
      const grant = resolved.grants.find((item) => item.entity_id !== null);
      if (!grant?.entity_id) throw new Error("No entity-scoped demo grant is available.");
      setSession(nextSession);
      setAuthContext(resolved);
      setWorkContext({
        entityId: grant.entity_id,
        module: grant.module ?? "attendance",
        classification: Math.min(1, grant.classification_ceiling) as 0 | 1 | 2 | 3,
      });
    } catch (error) {
      setConnectionError(errorMessage(error));
    } finally {
      setConnecting(false);
    }
  }

  async function handleUpload(file: File, context: WorkContext): Promise<void> {
    if (!session) return;
    setUploading(true);
    setUploadError(null);
    setUpload(null);
    setJob(null);
    setWorkContext(context);
    try {
      setUpload(await uploadDocument(session, context, file));
    } catch (error) {
      setUploadError(errorMessage(error));
    } finally {
      setUploading(false);
    }
  }

  async function handleQuery(question: string): Promise<void> {
    if (!session || !workContext) return;
    setQuerying(true);
    setQueryError(null);
    setAnswer(null);
    try {
      setAnswer(await askQuestion(session, workContext, question));
    } catch (error) {
      setQueryError(errorMessage(error));
    } finally {
      setQuerying(false);
    }
  }

  async function handleExport(format: ExportFormat): Promise<void> {
    if (!session || !workContext) return;
    setExporting(format);
    setExportMessage(null);
    setExportError(null);
    try {
      const result = await createAndDownloadExport(session, workContext, format);
      setExportMessage(`${format.toUpperCase()} export downloaded · ${result.record_count} records`);
    } catch (error) {
      setExportError(errorMessage(error));
    } finally {
      setExporting(null);
    }
  }

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Enterprise RAG demo</p>
          <h1>Attendance Intelligence</h1>
          <p>Upload evidence, ask a grounded question, inspect its sources, and export authorized records.</p>
        </div>
        <div className={`api-state api-state--${apiAvailable === null ? "checking" : apiAvailable ? "ready" : "error"}`}>
          <span aria-hidden="true" /> API {apiAvailable === null ? "checking" : apiAvailable ? "available" : "unavailable"}
        </div>
      </header>

      {!authContext || !session || !workContext ? (
        <AuthSetup busy={connecting} error={connectionError} onConnect={connect} />
      ) : (
        <>
          <div className="scope-strip">
            <span>Authorized session</span>
            <code>{authContext.tenant_id}</code>
            <span>{authContext.grants.length} grant{authContext.grants.length === 1 ? "" : "s"}</span>
          </div>
          <div className="workflow-grid">
            <UploadPanel
              busy={uploading}
              error={uploadError}
              grants={authContext.grants}
              onContextChange={setWorkContext}
              onUpload={handleUpload}
            />
            <ProcessingPanel job={job} upload={upload} />
          </div>
          <QueryPanel busy={querying} error={queryError} onAsk={handleQuery} />
          <AnswerPanel result={answer} />
          <ExportPanel
            busy={exporting}
            error={exportError}
            message={exportMessage}
            onExport={handleExport}
          />
        </>
      )}
      <footer>Backend authorization and validated evidence remain the source of truth.</footer>
    </main>
  );
}
