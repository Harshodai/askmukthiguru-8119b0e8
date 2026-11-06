/**
 * `lang` value for a teacher quote (NEW-A11Y-5, A11Y-07, WCAG 3.1.2).
 * Only a well-formed tag from the clip's own language field is used. The app
 * never detects a language by guessing; unknown means no attribute.
 */
const LANG_TAG = /^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$/;

export function quoteLang(language: string | null | undefined): string | undefined {
  if (!language || !LANG_TAG.test(language)) return undefined;
  const [primary, ...rest] = language.split('-');
  // Conventional casing: primary lower-case, a 2-letter region upper-case.
  return [primary.toLowerCase(), ...rest.map((p) => (p.length === 2 ? p.toUpperCase() : p))].join('-');
}
