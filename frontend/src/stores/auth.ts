import { defineStore } from 'pinia'
import { adminApi } from '@/api/admin'

export const useAuthStore = defineStore('auth', {
  state: () => ({ loggedIn: false }),
  actions: {
    async checkSession(): Promise<boolean> {
      try {
        await adminApi.getConfig()
        this.loggedIn = true
      } catch {
        this.loggedIn = false
      }
      return this.loggedIn
    },
    async login(username: string, password: string): Promise<void> {
      await adminApi.login(username, password)
      this.loggedIn = true
    },
    async isDefaultPassword(): Promise<boolean> {
      const cfg = await adminApi.getConfig()
      return cfg.password_is_default
    },
    async logout(): Promise<void> {
      try {
        await adminApi.logout()
      } finally {
        this.loggedIn = false
      }
    },
    async changePassword(oldPassword: string, newPassword: string): Promise<void> {
      await adminApi.changePassword(oldPassword, newPassword)
    },
  },
})
