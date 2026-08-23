import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { credentialRef } from '@deepseek-ai/dsh-credentials'
import { installSettingsSection, settingsNamespace } from '@deepseek-ai/dsh-settings'
import { launchEnvironmentOf } from '@deepseek-ai/dsh-launch-environment'
import { SearchHubFetchProvider, SearchHubSearchProvider, type SearchHubProviderOptions } from './provider.js'

export const name = 'searchhub-dsh-web'
export const inject = ['web']

const DEFAULT_URL_ENV = 'SEARCHHUB_URL'
const DEFAULT_TOKEN_ENV = 'SEARCHHUB_TOKEN'

export interface Config {
  baseURL?: string
  token?: string
  tokenEnv?: string
}

export const Config: z<Config> = z.object({
  baseURL: z.string().role('url'),
  token: z.string().role('secret'),
  tokenEnv: z.string().role('credential-ref').default(DEFAULT_TOKEN_ENV),
})

export const WEB_SEARCHHUB_SETTINGS_NAMESPACE = settingsNamespace('searchhub-dsh-web')

function resolveOptions(ctx: Context, config: Config): SearchHubProviderOptions {
  const tokenEnv = credentialRef(config.tokenEnv ?? DEFAULT_TOKEN_ENV)
  const literalToken = config.token !== undefined && config.token.length > 0 ? config.token : undefined
  return {
    ...(literalToken === undefined ? {} : { token: literalToken }),
    resolveToken: async () => {
      const credentials = ctx.get('credentials')
      if (credentials !== undefined) return (await credentials.resolve(tokenEnv))?.value
      const ambient = launchEnvironmentOf(ctx).get(tokenEnv)
      return ambient !== undefined && ambient.value.length > 0 ? ambient.value : undefined
    },
    baseURL: config.baseURL ?? launchEnvironmentOf(ctx).get(DEFAULT_URL_ENV)?.value ?? 'http://127.0.0.1:8000',
  }
}

export function apply(ctx: Context, config: Config): void {
  let current: () => Config = () => config
  installSettingsSection(ctx, WEB_SEARCHHUB_SETTINGS_NAMESPACE, Config, config, {
    setSource: (source) => { current = source },
    onChange: () => {},
  })
  const opts = () => resolveOptions(ctx, current())
  ctx.web.registerSearchProvider(new SearchHubSearchProvider(opts))
  ctx.web.registerFetchProvider(new SearchHubFetchProvider(opts))
}
