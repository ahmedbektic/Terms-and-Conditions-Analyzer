/* Architecture note:
 * ThemeProvider is the single app-level owner of persisted color-mode state.
 * UI surfaces consume `useTheme()` instead of reading localStorage or mutating
 * document state directly, which keeps the theme seam replaceable and testable.
 */

import { createContext, type ReactNode, useContext, useEffect, useState } from 'react';

export type ThemeMode = 'dark' | 'light';

interface ThemeContextValue {
  theme: ThemeMode;
  toggleTheme: () => void;
}

interface ThemeProviderProps {
  children: ReactNode;
}

const DEFAULT_THEME_MODE: ThemeMode = 'dark';

export const THEME_STORAGE_KEY = 'tca.theme.mode';

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: ThemeProviderProps) {
  const [theme, setTheme] = useState<ThemeMode>(() => readStoredThemeMode());

  useEffect(() => {
    applyDocumentTheme(theme);
    persistThemeMode(theme);
  }, [theme]);

  return (
    <ThemeContext.Provider
      value={{
        theme,
        toggleTheme: () => {
          setTheme((previous) => (previous === 'dark' ? 'light' : 'dark'));
        },
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider.');
  }
  return context;
}

function readStoredThemeMode(): ThemeMode {
  const storage = getLocalStorage();
  if (!storage) {
    return DEFAULT_THEME_MODE;
  }

  const storedTheme = storage.getItem(THEME_STORAGE_KEY);
  return isThemeMode(storedTheme) ? storedTheme : DEFAULT_THEME_MODE;
}

function persistThemeMode(theme: ThemeMode) {
  const storage = getLocalStorage();
  if (!storage) {
    return;
  }

  storage.setItem(THEME_STORAGE_KEY, theme);
}

function applyDocumentTheme(theme: ThemeMode) {
  if (typeof document === 'undefined') {
    return;
  }

  document.documentElement.dataset.theme = theme;
}

function getLocalStorage(): Storage | null {
  try {
    if (typeof window === 'undefined') {
      return null;
    }
    return window.localStorage;
  } catch {
    return null;
  }
}

function isThemeMode(value: string | null): value is ThemeMode {
  return value === 'dark' || value === 'light';
}
