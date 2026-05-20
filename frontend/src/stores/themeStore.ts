import { create } from 'zustand'

interface ThemeState {
  theme: 'dark' | 'light'
  toggleTheme: () => void
}

export const useThemeStore = create<ThemeState>((set) => {
  const initialTheme = (localStorage.getItem('theme') as 'dark' | 'light') || 'dark'
  document.documentElement.setAttribute('data-theme', initialTheme)
  
  return {
    theme: initialTheme,
    toggleTheme: () => set((state) => {
      const nextTheme = state.theme === 'dark' ? 'light' : 'dark'
      localStorage.setItem('theme', nextTheme)
      document.documentElement.setAttribute('data-theme', nextTheme)
      return { theme: nextTheme }
    })
  }
})
