import { expect, test } from '@playwright/test'

// Full journey (register → upload → score → convert) needs live Supabase + OpenAI;
// run manually against a deployed stack. This smoke only needs the app server.
test.skip(!process.env.E2E_BASE_URL, 'set E2E_BASE_URL to run the smoke test')

test('landing renders with a register CTA', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('link', { name: /Ücretsiz Başla|Start for free/ })).toBeVisible()
})

test('anonymous /dashboard redirects to /login', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login$/)
})
