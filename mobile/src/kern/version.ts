/* Versionen „1.2.3“ vergleichen (Mindestversion aus app_info) */
export function versionTeile(v: string): number[] {
  return String(v || '0').split(/[.+-]/).slice(0, 3).map((x) => parseInt(x, 10) || 0).concat([0, 0, 0]).slice(0, 3);
}
export function versionVergleich(a: string, b: string): number {
  const x = versionTeile(a), y = versionTeile(b);
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] < y[i] ? -1 : 1;
  return 0;
}
export const zuAlt = (eigene: string, mindest: string | undefined | null) => !!mindest && versionVergleich(eigene, mindest) < 0;
