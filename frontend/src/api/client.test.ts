import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from './client'

describe('apiFetch', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('resolves with parsed JSON on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ hello: 'world' }),
      }),
    )

    const result = await apiFetch<{ hello: string }>('/ping')

    expect(result).toEqual({ hello: 'world' })
  })

  it('204 No Content ではJSONパースせずundefinedを返す（DELETE等）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        json: async () => {
          throw new Error('本文が無いのでJSONパースは呼ばれないはず')
        },
      }),
    )

    const result = await apiFetch('/products/1', { method: 'DELETE' })

    expect(result).toBeUndefined()
  })

  it('throws the server detail message on non-ok response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: '条件を1つ以上指定してください' }),
      }),
    )

    await expect(apiFetch('/simulations')).rejects.toThrow('条件を1つ以上指定してください')
  })

  it('falls back to a generic message when the body has no detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({}),
      }),
    )

    await expect(apiFetch('/simulations')).rejects.toThrow('500')
  })
})
