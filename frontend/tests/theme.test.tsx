import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { THEME_STORAGE_KEY, ThemeProvider, useTheme } from '../src/features/theme/ThemeProvider';

function ThemeHarness() {
  const { theme, toggleTheme } = useTheme();

  return (
    <>
      <span>{theme}</span>
      <button type="button" onClick={toggleTheme}>
        Toggle theme
      </button>
    </>
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe('ThemeProvider', () => {
  it('defaults to dark mode and applies the document theme when storage is empty', async () => {
    render(
      <ThemeProvider>
        <ThemeHarness />
      </ThemeProvider>,
    );

    expect(screen.getByText('dark')).toBeTruthy();
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('restores a saved light preference and persists the next toggle', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    const user = userEvent.setup();

    render(
      <ThemeProvider>
        <ThemeHarness />
      </ThemeProvider>,
    );

    expect(screen.getByText('light')).toBeTruthy();
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'));

    await user.click(screen.getByRole('button', { name: 'Toggle theme' }));

    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(screen.getByText('dark')).toBeTruthy();
  });
});
