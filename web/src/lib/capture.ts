export async function captureVideoFrame(video: HTMLVideoElement): Promise<Blob> {
  const width = video.videoWidth || video.clientWidth || 1280
  const height = video.videoHeight || video.clientHeight || 720
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) {
    throw new Error('Canvas rendering is not available.')
  }
  context.drawImage(video, 0, 0, width, height)
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
