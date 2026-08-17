export type Classification = 0 | 1 | 2 | 3;
export type ExportFormat = "json" | "xlsx" | "pdf";

export interface ApiSession {
  token: string;
  productId: string;
  tenantId: string;
}

export interface Grant {
  role_id: string;
  entity_id: string | null;
  module: string | null;
  classification_ceiling: Classification;
  permissions: string[];
}

export interface AuthorizationContext {
  user_id: string;
  product_id: string;
  tenant_id: string;
  grants: Grant[];
}

export interface WorkContext {
  entityId: string;
  module: string;
  classification: Classification;
}

export interface UploadResult {
  job_id: string;
  document_id: string;
  document_version_id: string;
  checksum: string;
  status: string;
  idempotent: boolean;
}

export interface IngestionJob {
  job_id: string;
  status: string;
  current_stage: string;
  document_id: string;
  document_version_id: string;
  extracted_unit_count: number;
  normalized_record_count: number;
  review_required_count: number;
  error_count: number;
  errors: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  evidence_id: string;
  chunk_id: string;
  document_version_id: string;
  source_locator: Record<string, unknown>;
  claim: string;
  validated: boolean;
}

export interface AnswerResult {
  answer: string;
  tenant_context: Record<string, string>;
  entity_context: Record<string, string[]>;
  role_context: Record<string, string[]>;
  citations: Citation[];
  confidence: { score: number; band: "high" | "medium" | "low" };
  retrieval_mode: string;
  request_id: string;
  audit_id: string;
  status: "answered" | "unavailable";
  unavailable_reason: string | null;
}

export interface ExportJob {
  export_id: string;
  status: string;
  format: ExportFormat;
  created_at: string;
  expires_at: string;
  record_count: number;
  error_code: string | null;
}
