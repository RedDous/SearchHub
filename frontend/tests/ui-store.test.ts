import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useUiStore } from '@/stores/ui'
import { lang } from '@/i18n'

describe('ui store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('defaults to light theme and zh', () => {
    const ui = useUiStore()
    expect(ui.theme).toBe('light')
    expect(ui.lang).toBe('zh')
  })

  it('persists theme and wallpaper', () => {
    const ui = useUiStore()
    ui.setTheme('dark')
    ui.setWallpaper('https://example.com/bg.jpg')
    expect(localStorage.getItem('sh_theme')).toBe('dark')
    expect(localStorage.getItem('sh_wallpaper')).toBe('https://example.com/bg.jpg')
  })

  it('setLang syncs i18n singleton', () => {
    const ui = useUiStore()
    ui.setLang('en')
    expect(lang.value).toBe('en')
    expect(localStorage.getItem('sh_lang')).toBe('en')
  })
})
