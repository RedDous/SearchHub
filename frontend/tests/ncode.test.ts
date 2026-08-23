import { createApp, h } from 'vue'
import { describe, expect, test } from 'vitest'
import { NCode } from 'naive-ui'

function render(props: Record<string, unknown>): string {
  const host = document.createElement('div')
  document.body.appendChild(host)
  createApp(h(NCode, props)).mount(host)
  return host.textContent ?? ''
}

describe('NCode usage in history expand', () => {
  test('renders content via the code prop (not value)', async () => {
    const text = render({ code: '{"limit": 5}', wordWrap: true })
    expect(text).toContain('{"limit": 5}')
  })

  test('value prop alone renders nothing', async () => {
    const text = render({ value: '{"limit": 5}', wordWrap: true })
    expect(text).not.toContain('{"limit": 5}')
  })
})
