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
