import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DashboardPage } from '../src/features/dashboard/DashboardPage';

const globalCssPath = join(dirname(fileURLToPath(import.meta.url)), '../src/styles/global.css');

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

function readGlobalCss(): string {
  return readFileSync(globalCssPath, 'utf8');
}

/** Slice of stylesheet from the mobile `@media (max-width: 640px)` block through just before the next top-level `@media`, if any. */
function sliceMobileDashboardMediaBlock(css: string): string {
  const mediaStart = css.indexOf('@media (max-width: 640px)');
  expect(mediaStart).toBeGreaterThanOrEqual(0);
  const searchFrom = mediaStart + '@media (max-width: 640px)'.length;
  const nextMedia = css.indexOf('\n@media ', searchFrom);
  const blockEnd = nextMedia === -1 ? css.length : nextMedia;
  return css.slice(mediaStart, blockEnd);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('Dashboard responsive layout (SCRUM-170)', () => {
  describe('stylesheet contract', () => {
    it('does not collapse the two-column dashboard at tablet-wide breakpoints', () => {
      const css = readGlobalCss();
      expect(css).not.toMatch(/max-width:\s*1220px/);
    });

    it('stacks dashboard columns into one track only inside the mobile breakpoint', () => {
      const css = readGlobalCss();
      const mobileBlock = sliceMobileDashboardMediaBlock(css);
      expect(mobileBlock).toContain('.dashboard-layout');
      expect(mobileBlock).toContain('grid-template-columns: minmax(0, 1fr)');
    });

    it('adds touch-sized minimum heights for primary dashboard actions on mobile', () => {
      const css = readGlobalCss();
      const mobileBlock = sliceMobileDashboardMediaBlock(css);
      expect(mobileBlock).toContain('.dashboard .button-primary');
      expect(mobileBlock).toContain('min-height: 44px');
    });
  });

  describe('DOM reading order', () => {
    it('places the primary (control) column before the analysis column in document order', async () => {
      const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? 'GET';
        if (url.endsWith('/reports') && method === 'GET') {
          return jsonResponse([]);
        }
        if (url.endsWith('/tracked-policies') && method === 'GET') {
          return jsonResponse([]);
        }
        throw new Error(`Unexpected request: ${method} ${url}`);
      });
      vi.stubGlobal('fetch', fetchMock);

      const { container } = render(<DashboardPage />);

      await waitFor(() =>
        expect(screen.getByText('No reports yet. Submit a terms agreement to create one.')).toBeTruthy(),
      );

      const layout = container.querySelector('.dashboard-layout');
      expect(layout).toBeTruthy();
      const columns = layout!.querySelectorAll(':scope > .dashboard-column');
      expect(columns.length).toBe(2);
      expect(columns[0]!.classList.contains('dashboard-column-primary')).toBe(true);
      expect(columns[1]!.classList.contains('dashboard-column-analysis')).toBe(true);

      const primary = columns[0]!;
      const analysis = columns[1]!;
      expect(primary.compareDocumentPosition(analysis) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });
  });
});
