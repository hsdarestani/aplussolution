/** Fail closed for privileged shift-card details until the admin identity is known. */
export function canViewAdminShiftExtraRows(email: string | null | undefined): boolean {
  const normalized = String(email || '').trim().toLowerCase();
  return normalized.length > 0 && normalized !== 'info@aplus-solution.de';
}
