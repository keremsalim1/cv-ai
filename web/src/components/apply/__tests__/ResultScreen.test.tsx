import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import { ResultScreen } from '@/components/apply/ResultScreen'

const downloadBlob = vi.fn()
vi.mock('@/lib/download', () => ({ downloadBlob: (...a: unknown[]) => downloadBlob(...a) }))

beforeEach(() => vi.clearAllMocks())

it('submitted mode shows the screenshot', () => {
  renderWithIntl(
    <ResultScreen mode="submitted" screenshot="AAAA" pdf={new Blob(['%PDF'])}
      pdfName="Ada.pdf" coverLetter="cl" answers={[]} />
  )
  const img = screen.getByRole('img') as HTMLImageElement
  expect(img.src).toContain('data:image/png;base64,AAAA')
})

it('delivered mode downloads the PDF', async () => {
  renderWithIntl(
    <ResultScreen mode="delivered" pdf={new Blob(['%PDF'])} pdfName="Ada.pdf"
      coverLetter="my letter" answers={[]} />
  )
  await userEvent.click(screen.getByRole('button', { name: 'ATS PDF indir' }))
  expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'Ada.pdf')
})
