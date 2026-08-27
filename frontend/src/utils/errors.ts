/**
 * Turns an ExtractionJob.error_message (written for the backend's own logs,
 * not end users -- it can include a raw SDK exception's message) into a
 * short, actionable line for the AI Processing Monitor. Only relabels
 * patterns the backend is actually known to produce (see apps.extraction.
 * services.*.py's exception messages) -- never invents a cause, and falls
 * back to the backend's own (already secret-free) message untouched.
 *
 * `willRetry` must reflect the job's *current* status (pass `true` only
 * while it's actually 'retrying') -- a job that already exhausted
 * EXTRACTION_MAX_RETRIES and landed in 'failed' must not still say "this
 * will retry automatically", even though the underlying message text (e.g.
 * "Failed after 3 retries: OpenAI rate limit hit: ...") still mentions the
 * same root cause.
 */
export function humanizeExtractionError(message: string, willRetry: boolean): string {
  if (!message) return '';
  const lower = message.toLowerCase();
  const retryNote = willRetry
    ? ' This will retry automatically.'
    : ' All automatic retries were exhausted — try starting extraction again once the underlying issue is resolved.';

  if (lower.includes('rate limit') || lower.includes('insufficient_quota') || lower.includes('quota')) {
    return `The AI service is temporarily unavailable (rate limit or quota exceeded).${retryNote}`;
  }
  if (lower.includes('timed out')) {
    return `The AI service took too long to respond.${retryNote}`;
  }
  if (lower.includes('could not reach openai')) {
    return `Could not reach the AI service.${retryNote}`;
  }
  if (lower.includes('could not parse pdf')) {
    return 'This document could not be read — it may be corrupted, password-protected, or not a valid PDF.';
  }
  if (lower.includes('no file attached')) {
    return 'This document has no file attached and cannot be processed.';
  }
  if (lower.includes('openai_api_key') || lower.includes('openai_extraction_model') || lower.includes('not set')) {
    return 'The AI service is not configured on the server. Contact your administrator.';
  }
  if (lower.includes('server error')) {
    return `The AI service reported an internal error.${retryNote}`;
  }
  return message;
}

/**
 * Normalizes DRF's error response shapes into one display string:
 * - `{"detail": "..."}` (permission/auth/not-found errors)
 * - `{"field_name": ["message", ...], ...}` (serializer validation errors)
 * - `{"non_field_errors": ["message"]}` (serializer-level validation)
 */
export function getErrorMessage(err: any, fallback = 'Something went wrong. Please try again.'): string {
  const data = err?.response?.data;
  if (!data) return err?.message || fallback;
  if (typeof data === 'string') return data;
  if (data.detail) return data.detail;
  if (data.non_field_errors?.length) return data.non_field_errors[0];

  const firstField = Object.keys(data)[0];
  if (firstField) {
    const value = data[firstField];
    const message = Array.isArray(value) ? value[0] : value;
    if (typeof message === 'string') {
      return firstField === 'non_field_errors' ? message : `${firstField}: ${message}`;
    }
  }
  return fallback;
}
