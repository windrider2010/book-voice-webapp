export async function attemptPlayback(audio: HTMLAudioElement): Promise<boolean> {
  try {
    audio.currentTime = 0
    await audio.play()
    return false
  } catch {
    return true
  }
}
