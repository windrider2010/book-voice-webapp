<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

import { submitReadRequest } from './lib/api'
import { captureVideoFrame } from './lib/capture'
import { attemptPlayback } from './lib/playback'

const videoRef = ref<HTMLVideoElement | null>(null)
const audioRef = ref<HTMLAudioElement | null>(null)
const streamRef = ref<MediaStream | null>(null)

const cameraReady = ref(false)
const requestingCamera = ref(false)
const isSubmitting = ref(false)
const statusMessage = ref('Open the camera and frame a single page.')
const errorMessage = ref('')
const recognizedText = ref('')
const audioUrl = ref('')
const needsManualPlay = ref(false)

const canCapture = computed(() => cameraReady.value && !isSubmitting.value)

function stopStream(): void {
  streamRef.value?.getTracks().forEach((track) => track.stop())
  streamRef.value = null
}

async function startCamera(): Promise<void> {
  errorMessage.value = ''
  statusMessage.value = 'Requesting camera access...'
  requestingCamera.value = true

  if (!navigator.mediaDevices?.getUserMedia) {
    requestingCamera.value = false
    statusMessage.value = 'Camera unavailable'
    errorMessage.value = 'This browser does not expose camera access. Open the app in iPhone Safari over HTTPS.'
    return
  }

  try {
    stopStream()
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: 'environment' },
      },
    })
    streamRef.value = stream
    if (videoRef.value) {
      videoRef.value.srcObject = stream
      if (typeof videoRef.value.play === 'function') {
        await videoRef.value.play().catch(() => undefined)
      }
    }
    cameraReady.value = true
    statusMessage.value = 'Camera ready. Tap capture when the page is sharp.'
  } catch (error) {
    cameraReady.value = false
    statusMessage.value = 'Camera blocked'
    if (error instanceof DOMException && error.name === 'NotAllowedError') {
      errorMessage.value = 'Camera permission was denied. Allow camera access in Safari and try again.'
    } else {
      errorMessage.value = 'Unable to open the camera. Reload the page and try again.'
    }
  } finally {
    requestingCamera.value = false
  }
}

async function captureAndRead(): Promise<void> {
  if (!videoRef.value || !cameraReady.value) {
    return
  }

  errorMessage.value = ''
  isSubmitting.value = true
  statusMessage.value = 'Uploading frame and generating audio...'
  needsManualPlay.value = false

  try {
    const blob = await captureVideoFrame(videoRef.value)
    const payload = await submitReadRequest(blob)
    recognizedText.value = payload.text
    audioUrl.value = payload.audio_url
    statusMessage.value = 'Audio ready.'
    await nextTick()
    if (audioRef.value) {
      needsManualPlay.value = await attemptPlayback(audioRef.value)
      if (needsManualPlay.value) {
        statusMessage.value = 'Audio is ready. Safari requires one more tap to play it.'
      }
    }
  } catch (error) {
    statusMessage.value = 'Read failed'
    errorMessage.value = error instanceof Error ? error.message : 'The read request failed.'
  } finally {
    isSubmitting.value = false
  }
}

async function playAudio(): Promise<void> {
  if (!audioRef.value) {
    return
  }
  needsManualPlay.value = await attemptPlayback(audioRef.value)
}

onBeforeUnmount(() => {
  stopStream()
})
</script>

<template>
  <main class="shell">
    <section class="panel">
      <div class="hero">
        <p class="eyebrow">iPhone Book Reader</p>
        <h1>Point at a page. Capture once. Listen immediately.</h1>
        <p class="lede">
          The browser handles the camera, the server handles OCR and speech, and the phone stays on one screen.
        </p>
      </div>

      <div class="camera-card">
        <video ref="videoRef" autoplay muted playsinline class="preview" />
        <div class="camera-overlay">
          <div class="page-frame"></div>
        </div>
      </div>

      <div class="actions">
        <button class="primary" :disabled="requestingCamera || isSubmitting" @click="startCamera">
          {{ cameraReady ? 'Restart Camera' : requestingCamera ? 'Opening…' : 'Open Camera' }}
        </button>
        <button class="capture" :disabled="!canCapture" @click="captureAndRead">
          {{ isSubmitting ? 'Reading…' : 'Capture & Read' }}
        </button>
      </div>

      <p class="status">{{ statusMessage }}</p>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>

      <section v-if="recognizedText" class="result">
        <div class="result-header">
          <h2>OCR Text</h2>
          <span>server-rendered</span>
        </div>
        <pre class="text-preview">{{ recognizedText }}</pre>
        <audio v-if="audioUrl" ref="audioRef" :src="audioUrl" controls preload="auto" class="audio-player"></audio>
        <button v-if="needsManualPlay" class="secondary" @click="playAudio">Play Audio</button>
      </section>
    </section>
  </main>
</template>
