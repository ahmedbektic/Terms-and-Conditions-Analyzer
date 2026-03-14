/**
 * Shared date formatter for dashboard view models.
 * This keeps time formatting consistent between history rows and report detail.
 */
export function formatDashboardDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}
