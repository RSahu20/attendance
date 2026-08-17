import type {
  AnswerResult,
  ApiSession,
  AuthorizationContext,
  ExportFormat,
  ExportJob,
  IngestionJob,
  UploadResult,
  WorkContext,
} from "./types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

function authHeaders(session: ApiSession): Record<string, string> {
  return {
    Authorization: `Bearer ${session.token}`,
    "X-Product-ID": session.productId,
    "X-Tenant-ID": session.tenantId,
  };
}

async function safeError(response: Response): Promise<ApiError> {
  if (response.status === 401) return new ApiError("Authentication failed. Check the demo token.", 401);
  if (response.status === 403) return new ApiError("This operation is not authorized for the selected context.", 403);
  try {
    const body = (await response.json()) as { detail?: string };
    return new ApiError(body.detail || "The request could not be completed.", response.status);
  } catch {
    return new ApiError("The request could not be completed.", response.status);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, init);
  } catch {
    throw new ApiError("The backend is unavailable. Confirm Docker Compose is running.", 0);
  }
  if (!response.ok) throw await safeError(response);
  return (await response.json()) as T;
}

export function getAuthorizationContext(session: ApiSession): Promise<AuthorizationContext> {
  return request("/api/v1/auth/context", { headers: authHeaders(session) });
}

export async function uploadDocument(
  session: ApiSession,
  context: WorkContext,
  file: File,
): Promise<UploadResult> {
  let uploadFile = file;
  if (typeof file.arrayBuffer === "function") {
    try {
      const bytes = await file.arrayBuffer();
      uploadFile = new File([bytes], file.name, {
        type: file.type || "application/octet-stream",
        lastModified: file.lastModified,
      });
    } catch {
      throw new ApiError(
        "The browser cannot read this local file. Copy it to a local folder, select it again, or use a built-in sample.",
        0,
      );
    }
  }
  const body = new FormData();
  body.append("file", uploadFile);
  body.append("entity_id", context.entityId);
  body.append("module", context.module);
  body.append("classification", String(context.classification));
  body.append("logical_name", file.name.replace(/\.[^.]+$/, ""));
  return request<UploadResult>("/api/v1/documents", {
    method: "POST",
    headers: authHeaders(session),
    body,
  }).catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 0) {
      throw new ApiError(
        "The browser could not send the selected file. Re-select a local file or use the built-in demo CSV.",
        0,
      );
    }
    throw error;
  });
}

export function getIngestionJob(session: ApiSession, jobId: string): Promise<IngestionJob> {
  return request(`/api/v1/ingestion-jobs/${jobId}`, { headers: authHeaders(session) });
}

export function askQuestion(
  session: ApiSession,
  context: WorkContext,
  question: string,
): Promise<AnswerResult> {
  return request("/api/v1/queries", {
    method: "POST",
    headers: { ...authHeaders(session), "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      entity_id: context.entityId,
      module: context.module,
      classification: context.classification,
      filters: {},
    }),
  });
}

export async function createAndDownloadExport(
  session: ApiSession,
  context: WorkContext,
  format: ExportFormat,
): Promise<ExportJob> {
  const job = await request<ExportJob>("/api/v1/exports", {
    method: "POST",
    headers: { ...authHeaders(session), "Content-Type": "application/json" },
    body: JSON.stringify({
      format,
      dataset: "attendance",
      entity_id: context.entityId,
      module: context.module,
      classification: context.classification,
    }),
  });
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/v1/exports/${job.export_id}/download`, {
      headers: authHeaders(session),
    });
  } catch {
    throw new ApiError("The backend became unavailable while downloading the export.", 0);
  }
  if (!response.ok) throw await safeError(response);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `attendance-export-${job.export_id}.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return job;
}
