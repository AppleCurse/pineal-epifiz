import { writable } from 'svelte/store';

export type ThemeMode = 'dark' | 'light';

export type CockpitTab =
  | 'home'
  | 'cross'
  | 'aspasia'
  | 'lilith'
  | 'company'
  | 'media'
  | 'browser'
  | 'reports'
  | 'system';

const THEME_STORAGE_KEY = 'pineal_theme';

function readInitialTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'dark';
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    /* localStorage erişilemezse varsayılan koyu tema kullanılır */
  }
  return 'dark';
}

function applyThemeToDom(mode: ThemeMode) {
  if (typeof document !== 'undefined' && document.documentElement) {
    document.documentElement.dataset.theme = mode;
  }
}

const initialTheme = readInitialTheme();
applyThemeToDom(initialTheme);

export const theme = writable<ThemeMode>(initialTheme);

theme.subscribe((mode) => {
  applyThemeToDom(mode);
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, mode);
    } catch {
      /* sessizce geç */
    }
  }
});

export function toggleTheme(): void {
  theme.update((curr) => (curr === 'dark' ? 'light' : 'dark'));
}

export const activeTab = writable<CockpitTab>('home');
export const sidebarOpen = writable<boolean>(false);
