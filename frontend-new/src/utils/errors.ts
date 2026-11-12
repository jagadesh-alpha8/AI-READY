/** One readable sentence from an API error (DRF `detail`, field errors, or the network failure). */
export function errorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  const e = error as { response?: { status?: number; data?: unknown }; message?: string } | null;
  if (!e) return fallback;
  if (!e.response) return e.message === 'Network Error' ? 'The server could not be reached. Check that the backend is running.' : (e.message || fallback);
  const { status, data } = e.response;
  if (status === 403) return detailOf(data) || 'Your role does not have access to this.';
  if (status === 404) return detailOf(data) || 'Not found.';
  if (status === 429) return detailOf(data) || 'Too many attempts. Please wait and try again.';
  if (status && status >= 500) return 'The server had a problem handling this request.';
  return detailOf(data) || fallback;
}

function detailOf(data: unknown): string {
  if (!data) return '';
  if (typeof data === 'string') return data.length < 300 ? data : '';
  if (Array.isArray(data)) return data.map((d) => detailOf(d)).filter(Boolean).join(' ');
  if (typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if (typeof obj.detail === 'string') return obj.detail;
    return Object.entries(obj)
      .map(([field, msg]) => {
        const text = detailOf(msg);
        if (!text) return '';
        return field === 'non_field_errors' ? text : `${field.replace(/_/g, ' ')}: ${text}`;
      })
      .filter(Boolean)
      .join(' ');
  }
  return '';
}

/** HTTP status of an API error, if any. */
export const statusOf = (error: unknown): number | undefined =>
  (error as { response?: { status?: number } } | null)?.response?.status;
