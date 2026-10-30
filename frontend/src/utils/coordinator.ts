/**
 * IQAC Coordinator name / email checks -- the same rules the backend applies (apps/institutions/coordinator.py:
 * clean_name, clean_email), so the form explains a problem before sending. The server still decides.
 */

const NAME_FORBIDDEN = /[\d<>{}[\]()@#$%^&*=+|\/;:"!?~`_,]/;

export function coordinatorNameError(value: string): string {
  const name = value.replace(/\s+/g, ' ').trim();
  if (!name) return "Enter the IQAC Coordinator's name.";
  if (name.length < 2 || name.length > 150) return 'The name must be 2 to 150 characters.';
  const letters = Array.from(name).filter((ch) => /\p{L}/u.test(ch)).length;
  if (NAME_FORBIDDEN.test(name) || letters < 2) {
    return 'The name may contain letters, spaces, dots, hyphens and apostrophes only.';
  }
  return '';
}

export function coordinatorEmailError(value: string): string {
  const email = value.trim();
  if (!email) return "Enter the IQAC Coordinator's email address.";
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return 'Enter a valid email address.';
  return '';
}
