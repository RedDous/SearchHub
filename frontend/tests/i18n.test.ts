import { beforeEach, describe, expect, it } from 'vitest'
import { messages, setLang, t } from '@/i18n/index'

describe('i18n', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('translates known keys in zh and en', () => {
    setLang('zh')
    expect(t('login.title')).toBe(messages.zh['login.title'])
    setLang('en')
    expect(t('login.title')).toBe(messages.en['login.title'])
  })

  it('falls back to the key itself when missing', () => {
    expect(t('no.such.key')).toBe('no.such.key')
  })

  it('persists language to localStorage', () => {
    setLang('en')
    expect(localStorage.getItem('sh_lang')).toBe('en')
  })
})
