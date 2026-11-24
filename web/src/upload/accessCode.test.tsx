// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { readAccessCode } from '../api/accessCode'
import { MISSING_CODE_MESSAGE } from '../api/http'
import { UploadScreen } from './UploadScreen'

const pdf = () => new File(['%PDF'], 'cv.pdf', { type: 'application/pdf' })

function pick(file: File) {
  const input = screen.getByLabelText('CV file') as HTMLInputElement
  fireEvent.change(input, { target: { files: [file] } })
}

// Node 25 defines its own experimental localStorage, which shadows jsdom's and is unusable without
// --localstorage-file, so the tests install an in-memory Storage.
function memoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() {
      return data.size
    },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, String(v)),
  }
}

beforeEach(() => {
  Object.defineProperty(window, 'localStorage', { value: memoryStorage(), configurable: true })
})

afterEach(() => cleanup())

describe('access code on the upload screen', () => {
  it('is not shown in demo mode', () => {
    render(<UploadScreen rejection={null} demo onFile={() => {}} onReject={() => {}} />)
    expect(screen.queryByLabelText('Access code')).toBeNull()
  })

  it('blocks the upload until a code is entered, then stores it', () => {
    const onFile = vi.fn()
    render(<UploadScreen rejection={null} demo={false} needsAccessCode onFile={onFile} onReject={() => {}} />)
    pick(pdf())
    expect(onFile).not.toHaveBeenCalled()
    expect(screen.getByRole('alert').textContent).toBe(MISSING_CODE_MESSAGE)

    fireEvent.change(screen.getByLabelText('Access code'), { target: { value: ' secret-1 ' } })
    expect(screen.queryByRole('alert')).toBeNull()
    pick(pdf())
    expect(onFile).toHaveBeenCalledTimes(1)
    expect(readAccessCode()).toBe('secret-1')
  })

  it('prefills the stored code', () => {
    window.localStorage.setItem('dou-cv-analyzer.accessCode', 'stored-2')
    render(<UploadScreen rejection={null} demo={false} needsAccessCode onFile={() => {}} onReject={() => {}} />)
    expect((screen.getByLabelText('Access code') as HTMLInputElement).value).toBe('stored-2')
  })
})
