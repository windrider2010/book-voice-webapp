interface CoverCrop {
  sourceX: number
  sourceY: number
  sourceWidth: number
  sourceHeight: number
}

interface VideoFrameGeometry {
  videoWidth: number
  videoHeight: number
  clientWidth: number
  clientHeight: number
}

export function getVisibleVideoCrop(video: VideoFrameGeometry): CoverCrop {
  const sourceWidth = Math.max(1, video.videoWidth || video.clientWidth || 1280)
  const sourceHeight = Math.max(1, video.videoHeight || video.clientHeight || 720)
  const frameWidth = Math.max(1, video.clientWidth || sourceWidth)
  const frameHeight = Math.max(1, video.clientHeight || sourceHeight)

  const sourceRatio = sourceWidth / sourceHeight
  const frameRatio = frameWidth / frameHeight

  if (sourceRatio > frameRatio) {
    const croppedWidth = sourceHeight * frameRatio
    return {
      sourceX: (sourceWidth - croppedWidth) / 2,
      sourceY: 0,
      sourceWidth: croppedWidth,
      sourceHeight,
    }
  }

  if (sourceRatio < frameRatio) {
    const croppedHeight = sourceWidth / frameRatio
    return {
      sourceX: 0,
      sourceY: (sourceHeight - croppedHeight) / 2,
      sourceWidth,
      sourceHeight: croppedHeight,
    }
  }

  return {
    sourceX: 0,
    sourceY: 0,
    sourceWidth,
    sourceHeight,
  }
}

export async function captureVideoFrame(video: HTMLVideoElement): Promise<Blob> {
  const crop = getVisibleVideoCrop(video)
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(crop.sourceWidth)
  canvas.height = Math.round(crop.sourceHeight)
  const context = canvas.getContext('2d')
  if (!context) {
    throw new Error('Canvas rendering is not available.')
  }
  context.drawImage(
    video,
    crop.sourceX,
    crop.sourceY,
    crop.sourceWidth,
    crop.sourceHeight,
    0,
    0,
    canvas.width,
    canvas.height,
  )
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error('Unable to capture a frame from the camera preview.'))
        return
      }
      resolve(blob)
    }, 'image/jpeg', 0.92)
  })
}
