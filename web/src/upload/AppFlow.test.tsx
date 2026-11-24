// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMockApi, MOCK_FAILURE_MESSAGE } from '../api/mock'
import type { JobStatus, MatchApi } from '../api/types'
import { exampleResponse } from '../data'
import { AppFlow } from './AppFlow'
import { PRIVACY_NOTE } from './UploadScreen'

afterEach(cleanup)

const cv = (name: string, bytes = 100) => new File([new Uint8Array(bytes)], name)

function choose(file: File) {
  fireEvent.change(screen.getByLabelText('CV file'), { target: { files: [file] } })
}

/** A MatchApi whose answers the test releases one by one. */
function controlledApi() {
  const pending: ((v: unknown) => void)[] = []
  const next = <T,>() => new Promise<T>((resolve) => pending.push(resolve as (v: unknown) => void))
  const api: MatchApi = {
    uploadCv: vi.fn(() => next<{ jobId: string }>()),
    getJob: vi.fn(() => next<JobStatus>()),
  }
  const release = async (value: unknown) => {
    const resolve = pending.shift()
    if (!resolve) throw new Error('no pending call')
    await act(async () => {
      resolve(value)
    })
  }
  return { api, release }
}

describe('upload screen', () => {
  it('shows the drop zone, one accent button, the privacy note and the demo line', () => {
    const { container } = render(<AppFlow api={createMockApi()} demo />)
    expect(screen.getByTestId('drop-zone')).toBeTruthy()
    expect(container.querySelectorAll('.up-btn--accent')).toHaveLength(1)
    expect(screen.getByText(PRIVACY_NOTE)).toBeTruthy()
    expect(screen.getByText(/Demo mode/)).toBeTruthy()
    expect(screen.getByLabelText('CV file').getAttribute('accept')).toBe('.pdf,.docx,.txt')
  })

  it('rejects a wrong type and an oversized file inline, without calling the API', () => {
    const api = createMockApi()
    const upload = vi.spyOn(api, 'uploadCv')
    render(<AppFlow api={api} />)

    choose(cv('photo.png'))
    expect(screen.getByRole('alert').textContent).toBe('photo.png is not a PDF, DOCX or TXT file.')

    choose(cv('big.pdf', 5 * 1024 * 1024 + 1))
    expect(screen.getByRole('alert').textContent).toBe('big.pdf is 5.0 MB; the limit is 5 MB.')

    expect(upload).not.toHaveBeenCalled()
    expect(screen.getByTestId('drop-zone')).toBeTruthy()
  })

  it('accepts a dropped file', async () => {
    render(<AppFlow api={createMockApi()} />)
    fireEvent.drop(screen.getByTestId('drop-zone'), { dataTransfer: { files: [cv('cv.docx')] } })
    expect(await screen.findByText('CV vs DOU AI/ML vacancies')).toBeTruthy()
    expect(await screen.findByRole('button', { name: 'New CV' })).toBeTruthy()
  })
})

describe('progress view', () => {
  it('marks the current step as the job moves', async () => {
    const { api, release } = controlledApi()
    render(<AppFlow api={api} />)
    choose(cv('cv.pdf'))

    const current = () => screen.getByRole('list').querySelector('[aria-current="step"]')?.textContent
    expect(screen.getByText('cv.pdf')).toBeTruthy()
    expect(current()).toContain('Uploading the file')

    await release({ jobId: 'j1' })
    await release({ state: 'parsing' })
    expect(current()).toContain('Reading skills from the CV')
    expect(within(screen.getByRole('list')).getAllByRole('listitem')[0]?.getAttribute('data-status')).toBe('done')

    await release({ state: 'matching' })
    expect(current()).toContain('Matching against vacancies')
  })
})

describe('flow', () => {
  it('upload -> results with the example data -> New CV -> upload', async () => {
    render(<AppFlow api={createMockApi({ delayMs: 0 })} />)
    choose(cv('cv.pdf'))

    const summary = await screen.findByTestId('summary')
    expect(summary.textContent).toContain(`Fits: 0 of ${exampleResponse.vacancies.length} vacancies`)
    // The rail shows experience, English and the top 8 skills; the other sliders are rendered but hidden.
    expect(screen.getAllByRole('slider')).toHaveLength(10)
    expect(screen.getAllByRole('slider', { hidden: true })).toHaveLength(31)
    expect(screen.getByText('Middle AI Engineer')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'New CV' }))
    expect(screen.getByTestId('drop-zone')).toBeTruthy()
    expect(screen.queryByTestId('summary')).toBeNull()
  })

  it('fail*.pdf -> error view; Retry uploads the same file again', async () => {
    const api = createMockApi({ delayMs: 0 })
    const upload = vi.spyOn(api, 'uploadCv')
    render(<AppFlow api={api} />)
    choose(cv('fail-cv.pdf'))

    expect((await screen.findByRole('alert')).textContent).toBe(MOCK_FAILURE_MESSAGE)
    expect(screen.getByText('fail-cv.pdf')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(upload).toHaveBeenCalledTimes(2)
    expect(upload.mock.calls[1]?.[0].name).toBe('fail-cv.pdf')
    expect((await screen.findByRole('alert')).textContent).toBe(MOCK_FAILURE_MESSAGE)
  })

  it('Retry after a failure can reach the results', async () => {
    let calls = 0
    const mock = createMockApi({ delayMs: 0 })
    const api: MatchApi = {
      uploadCv: (file) => (++calls === 1 ? Promise.reject(new Error('Upload failed: 503')) : mock.uploadCv(file)),
      getJob: (id) => mock.getJob(id),
    }
    render(<AppFlow api={api} />)
    choose(cv('cv.txt'))

    expect((await screen.findByRole('alert')).textContent).toBe('Upload failed: 503')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByTestId('summary')).toBeTruthy()
  })

  it('"Choose another file" on the error view returns to upload', async () => {
    render(<AppFlow api={createMockApi({ delayMs: 0 })} />)
    choose(cv('fail.pdf'))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Choose another file' }))
    expect(screen.getByTestId('drop-zone')).toBeTruthy()
  })
})
