import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'

vi.mock('./lib/api', () => ({
  submitReadRequest: vi.fn(),
}))

vi.mock('./lib/capture', () => ({
  captureVideoFrame: vi.fn(),
}))

vi.mock('./lib/playback', () => ({
  attemptPlayback: vi.fn(),
}))

import { submitReadRequest } from './lib/api'
import { captureVideoFrame } from './lib/capture'
import { attemptPlayback } from './lib/playback'

const getUserMedia = vi.fn()

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      value: { getUserMedia },
      configurable: true,
    })
    Object.defineProperty(HTMLMediaElement.prototype, 'play', {
      value: vi.fn().mockResolvedValue(undefined),
      configurable: true,
    })
    Object.defineProperty(HTMLVideoElement.prototype, 'srcObject', {
      value: null,
      writable: true,
      configurable: true,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows an error when camera APIs are unavailable', async () => {
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      value: undefined,
      configurable: true,
    })

    const wrapper = mount(App)
    await wrapper.get('button.primary').trigger('click')

    expect(wrapper.text()).toContain('does not expose camera access')
  })

  it('shows a permission error when Safari blocks camera access', async () => {
    getUserMedia.mockRejectedValue(new DOMException('blocked', 'NotAllowedError'))

    const wrapper = mount(App)
    await wrapper.get('button.primary').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Camera permission was denied')
  })

  it('shows a manual play button when autoplay is rejected', async () => {
    getUserMedia.mockResolvedValue({
      getTracks: () => [{ stop: vi.fn() }],
    })
    vi.mocked(captureVideoFrame).mockResolvedValue(new Blob(['img'], { type: 'image/jpeg' }))
    vi.mocked(submitReadRequest).mockResolvedValue({
      request_id: 'req-1',
      text: '你好 world',
      audio_url: '/media/audio/req-1',
      mime_type: 'audio/wav',
      expires_at: '2026-04-14T00:00:00Z',
    })
    vi.mocked(attemptPlayback).mockResolvedValue(true)

    const wrapper = mount(App)
    await wrapper.get('button.primary').trigger('click')
    await flushPromises()
    await wrapper.get('button.capture').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Audio is ready')
    expect(wrapper.text()).toContain('Play Audio')
    expect(wrapper.text()).toContain('你好 world')
  })
})
