import { describe, expect, it } from 'vitest'

import { getVisibleVideoCrop } from './capture'

describe('getVisibleVideoCrop', () => {
  it('crops the left and right edges when the source is wider than the viewport', () => {
    const crop = getVisibleVideoCrop({
      videoWidth: 1920,
      videoHeight: 1080,
      clientWidth: 360,
      clientHeight: 640,
    })

    expect(crop.sourceY).toBe(0)
    expect(Math.round(crop.sourceWidth)).toBe(608)
    expect(Math.round(crop.sourceX)).toBe(656)
  })

  it('crops the top and bottom edges when the source is taller than the viewport', () => {
    const crop = getVisibleVideoCrop({
      videoWidth: 1080,
      videoHeight: 1920,
      clientWidth: 640,
      clientHeight: 360,
    })

    expect(crop.sourceX).toBe(0)
    expect(Math.round(crop.sourceHeight)).toBe(608)
    expect(Math.round(crop.sourceY)).toBe(656)
  })

  it('returns the full frame when source and viewport aspect ratios match', () => {
    const crop = getVisibleVideoCrop({
      videoWidth: 1536,
      videoHeight: 2048,
      clientWidth: 375,
      clientHeight: 500,
    })

    expect(crop).toEqual({
      sourceX: 0,
      sourceY: 0,
      sourceWidth: 1536,
      sourceHeight: 2048,
    })
  })
})
