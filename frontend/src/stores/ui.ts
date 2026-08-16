import { defineStore } from 'pinia'
import { setLang as setI18nLang, type Lang } from '@/i18n'

type Theme = 'light' | 'dark'

function readStorage(key: string, fallback: string): string {
  return localStorage.getItem(key) ?? fallback
}

export const useUiStore = defineStore('ui', {
  state: () => ({
    theme: (readStorage('sh_theme', 'light') as Theme),
    lang: (readStorage('sh_lang', 'zh') as Lang),
    wallpaper: readStorage('sh_wallpaper', ''),
  }),
  actions: {
    setTheme(theme: Theme) {
      this.theme = theme
      localStorage.setItem('sh_theme', theme)
    },
    setLang(l: Lang) {
      this.lang = l
      setI18nLang(l)
      localStorage.setItem('sh_lang', l)
    },
    setWallpaper(url: string) {
      this.wallpaper = url
      localStorage.setItem('sh_wallpaper', url)
    },
  },
})
