import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const context = {
  user_id: "user-1",
  product_id: "product-1",
  tenant_id: "tenant-1",
  grants: [
    {
      role_id: "role-1",
      entity_id: "entity-1",
      module: "attendance",
      classification_ceiling: 2,
      permissions: ["document:write", "attendance:read", "attendance:export"],
    },
  ],
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function routeBase(url: string, init?: RequestInit): Response | undefined {
  if (url.endsWith("/health/live")) return json({ status: "alive" });
  if (url.endsWith("/api/v1/auth/context")) return json(context);
  return undefined;
}

async function connect(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.type(screen.getByLabelText("Bearer token"), "demo-token");
  await user.type(screen.getByLabelText("Product ID"), "product-1");
  await user.type(screen.getByLabelText("Tenant ID"), "tenant-1");
  await user.click(screen.getByRole("button", { name: "Connect" }));
  await screen.findByText("Authorized session");
}

describe("basic evaluator workflow", () => {
  beforeEach(() => {
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("uploads a file and renders its completed processing status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const base = routeBase(url, init);
        if (base) return base;
        if (url.endsWith("/attendance-demo.csv")) {
          return new Response("Date,Employee ID\n2026-01-05,DEMO-001", {
            status: 200,
            headers: { "Content-Type": "text/csv" },
          });
        }
        if (url.endsWith("/api/v1/documents")) {
          expect(init?.method).toBe("POST");
          expect(init?.body).toBeInstanceOf(FormData);
          return json({
            job_id: "job-1",
            document_id: "document-1",
            document_version_id: "version-1",
            checksum: "abc",
            status: "completed",
            idempotent: false,
          }, 201);
        }
        if (url.endsWith("/api/v1/ingestion-jobs/job-1")) {
          return json({
            job_id: "job-1",
            status: "completed",
            current_stage: "completed",
            document_id: "document-1",
            document_version_id: "version-1",
            extracted_unit_count: 3,
            normalized_record_count: 12,
            review_required_count: 1,
            error_count: 0,
            errors: [],
            created_at: "2026-08-15T00:00:00Z",
            updated_at: "2026-08-15T00:00:01Z",
          });
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    const user = userEvent.setup();
    render(<App />);
    await connect(user);
    await user.click(screen.getByRole("button", { name: "Use built-in demo CSV" }));
    expect(await screen.findByText("attendance-demo.csv")).toBeInTheDocument();
    expect(screen.getByText(/text\/csv/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Upload and process" }));
    expect(await screen.findByText("job-1")).toBeInTheDocument();
    expect(await screen.findByText("Processing completed successfully.")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("submits a question and renders the backend answer, citation, context, and confidence", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const base = routeBase(url, init);
        if (base) return base;
        if (url.endsWith("/api/v1/queries")) {
          expect(JSON.parse(String(init?.body)).question).toBe("Show supporting evidence");
          return json({
            answer: "SYN-001 was present on 2026-01-05.",
            tenant_context: { tenant_id: "tenant-1" },
            entity_context: { entity_ids: ["entity-1"] },
            role_context: { roles: ["role-1"] },
            citations: [
              {
                evidence_id: "CIT-001",
                chunk_id: "chunk-1",
                document_version_id: "version-1",
                source_locator: { source_file: "attendance.xlsx", sheet: "Attendance", row: 18 },
                claim: "SYN-001 was marked present.",
                validated: true,
              },
            ],
            confidence: { score: 0.91, band: "high" },
            retrieval_mode: "hybrid",
            request_id: "request-1",
            audit_id: "audit-1",
            status: "answered",
            unavailable_reason: null,
          });
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    const user = userEvent.setup();
    render(<App />);
    await connect(user);
    await user.type(screen.getByLabelText("Question"), "Show supporting evidence");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("SYN-001 was present on 2026-01-05.")).toBeInTheDocument();
    expect(screen.getByText("Confidence: HIGH")).toBeInTheDocument();
    expect(screen.getByText("0.91")).toBeInTheDocument();
    expect(screen.getByText("CIT-001")).toBeInTheDocument();
    expect(screen.getAllByText("attendance.xlsx")).toHaveLength(2);
    expect(screen.getByText("Attendance")).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getAllByText("tenant-1")).toHaveLength(2);
    expect(screen.getByText(/Request ID: request-1/)).toBeInTheDocument();
  });

  it("renders controlled unavailable evidence and a safe API error", async () => {
    let queryCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const base = routeBase(url, init);
        if (base) return base;
        if (url.endsWith("/api/v1/queries")) {
          queryCount += 1;
          if (queryCount === 2) return json({ detail: "Requested scope is unavailable" }, 403);
          return json({
            answer: "The answer is unavailable because sufficient authorized evidence could not be validated.",
            tenant_context: { tenant_id: "tenant-1" },
            entity_context: { entity_ids: ["entity-1"] },
            role_context: { roles: ["role-1"] },
            citations: [],
            confidence: { score: 0, band: "low" },
            retrieval_mode: "unsupported",
            request_id: "request-2",
            audit_id: "audit-2",
            status: "unavailable",
            unavailable_reason: "INSUFFICIENT_AUTHORIZED_EVIDENCE",
          });
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    const user = userEvent.setup();
    render(<App />);
    await connect(user);
    const question = screen.getByLabelText("Question");
    await user.type(question, "Predict next year's attendance");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("heading", { name: "Evidence unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Reason: INSUFFICIENT_AUTHORIZED_EVIDENCE")).toBeInTheDocument();
    expect(screen.getByText("Confidence: LOW")).toBeInTheDocument();
    await user.clear(question);
    await user.type(question, "Try an unauthorized query");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not authorized");
  });

  it("creates and downloads JSON, XLSX, and PDF exports through backend APIs", async () => {
    const formats: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const base = routeBase(url, init);
        if (base) return base;
        if (url.endsWith("/api/v1/exports") && init?.method === "POST") {
          const format = JSON.parse(String(init.body)).format as string;
          formats.push(format);
          return json({
            export_id: `export-${format}`,
            status: "completed",
            format,
            created_at: "2026-08-15T00:00:00Z",
            expires_at: "2026-08-15T01:00:00Z",
            record_count: 12,
            error_code: null,
          }, 201);
        }
        if (url.includes("/download")) return new Response("artifact", { status: 200 });
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    const user = userEvent.setup();
    render(<App />);
    await connect(user);
    for (const format of ["JSON", "XLSX", "PDF"]) {
      await user.click(screen.getByRole("button", { name: `Export ${format}` }));
      expect(await screen.findByText(`${format} export downloaded · 12 records`)).toBeInTheDocument();
    }
    expect(formats).toEqual(["json", "xlsx", "pdf"]);
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(3);
  });
});
