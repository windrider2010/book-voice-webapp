export interface ReadPayload {
  request_id: string
  text: string
  audio_url: string
  mime_type: string
  expires_at: string
}

export async function submitReadRequest(blob: Blob, langHint = 'bilingual'): Promise<ReadPayload> {
  const formData = new FormData()
  formData.append('image', blob, 'page.jpg')
  formData.append('lang_hint', langHint)

  const response = await fetch('/api/read', {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    let message = 'Upload failed.'
    try {
      const payload = await response.json()
      if (typeof payload.detail === 'string') {
        message = payload.detail
      }
    } catch {
      message = `${message} (${response.status})`
    }
    throw new Error(message)
  }

  return response.json() as Promise<ReadPayload>
}
