import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { AssistFillResult } from '@/types/api'
import { AssistScreen } from '@/components/apply/AssistScreen'

const FILLED: AssistFillResult = {
  status: 'filled', field_count: 2, screenshot: 'PNGDATA',
  filled: [{ label: 'Motivasyon', value: 'API severim' }],
}

it('fill button triggers onFill', async () => {
  const onFill = vi.fn()
  renderWithIntl(<AssistScreen result={null} busy={false} onFill={onFill} onFinish={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Formu doldur' }))
  expect(onFill).toHaveBeenCalled()
})

it('shows the filled summary and screenshot', () => {
  renderWithIntl(<AssistScreen result={FILLED} busy={false} onFill={vi.fn()} onFinish={vi.fn()} />)
  expect(screen.getByText(/2 alan dolduruldu/)).toBeInTheDocument()
  expect(screen.getByText(/API severim/)).toBeInTheDocument()
  expect((screen.getByRole('img') as HTMLImageElement).src).toContain('PNGDATA')
})

it('shows the no-form notice', () => {
  // an older server that sends no reason still gets a sensible message
  renderWithIntl(<AssistScreen result={{ status: 'no_form' }} busy={false} onFill={vi.fn()} onFinish={vi.fn()} />)
  expect(screen.getByText(/doldurulacak alan bulamadım/)).toBeInTheDocument()
})

it('names the fields the user still has to fill in by hand', () => {
  renderWithIntl(<AssistScreen busy={false} onFill={vi.fn()} onFinish={vi.fn()}
    result={{ ...FILLED, unfilled: [{ label: 'Ülke', reason: 'no visible option matched' }] }} />)
  expect(screen.getByText(/Ülke/)).toBeInTheDocument()
})

it('explains a login wall instead of just saying no form was found', () => {
  renderWithIntl(<AssistScreen result={{ status: 'no_form', reason: 'login_wall' }}
    busy={false} onFill={vi.fn()} onFinish={vi.fn()} />)
  // deliberately specific: the always-visible intro paragraph also mentions
  // signing in, so a loose /giriş/ would pass without any code change
  expect(screen.getByText(/giriş yapmanızı istiyor/)).toBeInTheDocument()
  expect(screen.queryByText(/doldurulacak alan bulamadım/)).not.toBeInTheDocument()
})

it('explains a captcha as its own reason', () => {
  renderWithIntl(<AssistScreen result={{ status: 'no_form', reason: 'captcha' }}
    busy={false} onFill={vi.fn()} onFinish={vi.fn()} />)
  expect(screen.getByText(/doğrulama/i)).toBeInTheDocument()
})

it('tells the user to reopen the browser when they closed it', () => {
  renderWithIntl(<AssistScreen result={{ status: 'no_form', reason: 'browser_closed' }}
    busy={false} onFill={vi.fn()} onFinish={vi.fn()} />)
  expect(screen.getByText(/tarayıcı penceresi kapanmış/)).toBeInTheDocument()
})

it('finish button triggers onFinish', async () => {
  const onFinish = vi.fn()
  renderWithIntl(<AssistScreen result={null} busy={false} onFill={vi.fn()} onFinish={onFinish} />)
  await userEvent.click(screen.getByRole('button', { name: 'Bitir' }))
  expect(onFinish).toHaveBeenCalled()
})
