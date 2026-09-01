export type DocumentStatus = 'pending' | 'uploaded' | 'processing' | 'processed' | 'failed' | 'rejected';

export interface SprintDocument {
  id: string;
  sprint_id: string;
  document_type: string;
  document_type_label: string;
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

export type DriveImportJobStatus = 'pending' | 'scanning' | 'downloading' | 'completed' | 'failed';

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

/**
 * Keyed by DRIVE_IMPORT_CHECKLIST type slug (backend/apps/documents/
 * constants.py) -> DriveImportChecklistResult, PLUS two fixed keys of a
 * different shape: 'unmatched_files' (string[]) and 'skipped_files'
 * (DriveImportSkippedFile[]). This mixed shape mirrors the backend's single
 * `results` JSONField exactly -- callers must filter those two keys out
 * before treating the rest as checklist results (see UploadDataPack.tsx).
 */
export interface DriveImportJobResults {
  [key: string]: DriveImportChecklistResult | string[] | DriveImportSkippedFile[];
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
