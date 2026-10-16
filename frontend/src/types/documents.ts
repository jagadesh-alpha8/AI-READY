export type DocumentStatus = 'pending' | 'uploaded' | 'processing' | 'processed' | 'failed' | 'rejected';

/** Who set `document_type`: the uploader, or the Drive importer's filename keywords. */
export type DocumentTypeSource = 'uploader' | 'filename' | 'none';

/** The AI classifier's verdict from reading the content (set during extraction). */
export type ClassificationStatus = 'pending' | 'classified' | 'needs_review' | 'unclassified';

export interface SprintDocument {
  id: string;
  sprint_id: string;
  /** The type assigned at upload/import -- never changed by the AI. */
  document_type: string;
  document_type_label: string;
  document_type_source: DocumentTypeSource;
  classification_status: ClassificationStatus;
  /** A checklist slug, or '' (unclassified / not yet categorized). Only a
   * 'classified' result counts toward the checklist. */
  ai_document_type: string;
  ai_document_type_label: string | null;
  ai_confidence: number | null;
  ai_reasoning: string;
  classified_at: string | null;
  /** Set when a person decided the category (POST /documents/{id}/confirm-category);
   * classification_status/ai_document_type then hold their decision and
   * reprocessing keeps it. ai_confidence/ai_reasoning stay the AI's last verdict. */
  category_confirmed_by: string | null;
  category_confirmed_by_name: string | null;
  category_confirmed_at: string | null;
  title: string;
  original_filename: string;
  mime_type: string;
  file_size: number | null;
  file_size_display: string | null;
  checksum: string;
  download_url: string | null;
  has_file: boolean;
  uploaded_by: string | null;
  owner_role: string;
  status: DocumentStatus;
  page_count: number | null;
  quality_score: number | null;
  ocr_required: boolean;
  ocr_warnings: string[];
  processing_status: string;
  uploaded_at: string | null;
  processed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type DriveImportJobStatus = 'pending' | 'scanning' | 'downloading' | 'completed' | 'failed' | 'cancelled';

export const ACTIVE_DRIVE_IMPORT_STATUSES: DriveImportJobStatus[] = ['pending', 'scanning', 'downloading'];

export interface DriveImportChecklistResult {
  status: 'found' | 'missing';
  filename: string | null;
  document_id: string | null;
}

export interface DriveImportSkippedFile {
  filename: string;
  reason: string;
}

/** A Drive file imported as a supporting document (no checklist slot).
 * `folder` is '' for the root folder, 'Reports/2024' for a subfolder. */
export interface DriveImportAdditionalFile {
  filename: string;
  folder: string;
  document_id: string;
}

/** Live per-file progress, rewritten after every file while the job runs. */
export interface DriveImportProgress {
  processed: number;
  total: number;
  current_file: string;
}

/**
 * Keyed by DRIVE_IMPORT_CHECKLIST type slug (backend/apps/documents/
 * constants.py) -> DriveImportChecklistResult, PLUS two fixed keys of a
 * different shape: 'additional_files' (DriveImportAdditionalFile[]) and
 * 'skipped_files' (DriveImportSkippedFile[]). This mixed shape mirrors the
 * backend's single `results` JSONField exactly -- callers must filter those
 * two keys out before treating the rest as checklist results (see
 * UploadDataPack.tsx). Older jobs may carry 'unmatched_files' (string[]).
 */
export interface DriveImportJobResults {
  [key: string]:
    | DriveImportChecklistResult
    | string[]
    | DriveImportSkippedFile[]
    | DriveImportAdditionalFile[]
    | DriveImportProgress;
}

export interface DriveImportJob {
  id: string;
  sprint_id: string;
  drive_url: string;
  status: DriveImportJobStatus;
  results: DriveImportJobResults;
  files_scanned: number;
  files_imported: number;
  error_message: string;
  created_by: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}
