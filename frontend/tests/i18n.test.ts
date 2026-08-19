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

  it('has force-change-password keys in both languages', () => {
    expect(messages.zh['setup.forceChangeTitle']).toBe('请修改默认密码')
    expect(messages.zh['setup.forceChangeDesc']).toBe('您正在使用默认密码，出于安全考虑请立即修改。')
    expect(messages.en['setup.forceChangeTitle']).toBe('Change the default password')
    expect(messages.en['setup.forceChangeDesc']).toBe('You are using the default password. Please change it now.')
  })
})
