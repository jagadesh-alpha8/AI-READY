/** Query params without empty values (an empty filter means "all"). */
export function cleanParams(params: Record<string, string | number | boolean | undefined | null>) {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v !== undefined && v !== null));
}
