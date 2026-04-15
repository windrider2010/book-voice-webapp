<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

import { submitReadRequest } from './lib/api'
import { captureVideoFrame } from './lib/capture'
import { attemptPlayback } from './lib/playback'

type ThemeId = 'frozen' | 'arendelle' | 'moana'

interface ThemeOption {
  id: ThemeId
  label: string
  hint: string
  eyebrow: string
  title: string
  lede: string
  resultTag: string
}

const themes: ThemeOption[] = [
  {
    id: 'frozen',
    label: 'Frozen',
    hint: 'Ice hall glow',
    eyebrow: 'Frozen Light',
    title: 'Use a wider ice-lit camera stage for the page.',
    lede: 'The live preview now dominates the screen, with a broad guide so the full page can fill the frame instead of only the center.',
    resultTag: 'ice-tuned layout',
  },
  {
    id: 'arendelle',
    label: 'Arendelle',
    hint: 'Royal harbor calm',
    eyebrow: 'Arendelle Library',
    title: 'Turn the phone into a calmer royal reading window.',
    lede: 'A statelier palette, a larger live view, and a cleaner reading deck keep capture and playback on one screen.',
    resultTag: 'kingdom mode',
  },
  {
    id: 'moana',
    label: 'Moana',
    hint: 'Ocean voyage warmth',
    eyebrow: 'Open Ocean',
    title: 'Frame the page in a bright tide and read on the move.',
    lede: 'The guide stays wide and vivid, which works better outdoors and keeps the capture area legible even in glare.',
    resultTag: 'voyager mode',
  },
]
const defaultTheme: ThemeOption = themes[0]!

const videoRef = ref<HTMLVideoElement | null>(null)
const audioRef = ref<HTMLAudioElement | null>(null)
const streamRef = ref<MediaStream | null>(null)

const themeId = ref<ThemeId>('frozen')
const cameraReady = ref(false)
const requestingCamera = ref(false)
const isSubmitting = ref(false)
const statusMessage = ref('Open the camera and let the page fill most of the guide.')
const errorMessage = ref('')
const recognizedText = ref('')
const audioUrl = ref('')
const needsManualPlay = ref(false)

const activeTheme = computed<ThemeOption>(() => themes.find((theme) => theme.id === themeId.value) ?? defaultTheme)
const canCapture = computed(() => cameraReady.value && !isSubmitting.value)

function selectTheme(id: ThemeId): void {
  themeId.value = id
}

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
        width: { ideal: 1920 },
        height: { ideal: 2560 },
        aspectRatio: { ideal: 0.75 },
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
    statusMessage.value = 'Camera ready. Let the page fill the guide before capture.'
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
  statusMessage.value = 'Uploading the visible frame and generating audio...'
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
  <main class="shell" :data-theme="themeId">
    <section class="panel">
      <header class="topbar">
        <div class="brand">
          <div>
            <p class="brand-mark">Book Voice</p>
            <span class="brand-subtitle">iPhone camera + server OCR + server speech</span>
          </div>
          <div class="hero-notes">
            <span class="badge">bigger live view</span>
            <span class="badge">single-page capture</span>
            <span class="badge">instant replay</span>
          </div>
        </div>

        <div class="theme-picker" role="tablist" aria-label="Theme picker">
          <button
            v-for="theme in themes"
            :key="theme.id"
            type="button"
            class="theme-pill"
            :class="{ active: theme.id === themeId }"
            :aria-pressed="theme.id === themeId"
            :data-theme-choice="theme.id"
            @click="selectTheme(theme.id)"
          >
            <span class="theme-pill__name">{{ theme.label }}</span>
            <span class="theme-pill__hint">{{ theme.hint }}</span>
          </button>
        </div>
      </header>

      <section class="hero">
        <p class="eyebrow">{{ activeTheme.eyebrow }}</p>
        <h1>{{ activeTheme.title }}</h1>
        <p class="lede">{{ activeTheme.lede }}</p>
      </section>

      <section class="camera-stage">
        <div class="camera-card">
          <video ref="videoRef" autoplay muted playsinline class="preview" />
          <div class="camera-overlay">
            <div class="frame-copy">
              <span class="frame-chip">Let the page fill most of the frame.</span>
              <span class="frame-chip subtle">Keep the text sharp before capture.</span>
            </div>
            <div class="page-frame" aria-hidden="true">
              <span class="corner corner--tl"></span>
              <span class="corner corner--tr"></span>
              <span class="corner corner--bl"></span>
              <span class="corner corner--br"></span>
            </div>
          </div>
          <div v-if="isSubmitting" class="processing-overlay" role="status" aria-live="polite">
            <div class="processing-card">
              <div class="processing-orbit" aria-hidden="true">
                <span></span>
                <span></span>
                <span></span>
              </div>
              <div class="processing-copy">
                <p class="processing-title">Reading the page...</p>
                <p>Uploading, OCR, and speech synthesis are in progress.</p>
              </div>
            </div>
          </div>
        </div>

        <div class="actions">
          <button type="button" class="primary" :disabled="requestingCamera || isSubmitting" @click="startCamera">
            {{ cameraReady ? 'Restart Camera' : requestingCamera ? 'Opening...' : 'Open Camera' }}
          </button>
          <button type="button" class="capture" :disabled="!canCapture" @click="captureAndRead">
            {{ isSubmitting ? 'Reading...' : 'Capture & Read' }}
          </button>
        </div>

        <div class="status-card">
          <p class="status-label">Status</p>
          <p class="status">{{ statusMessage }}</p>
          <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
        </div>
      </section>

      <section v-if="recognizedText" class="result">
        <div class="result-header">
          <h2>OCR Text</h2>
          <span>{{ activeTheme.resultTag }}</span>
        </div>
        <pre class="text-preview">{{ recognizedText }}</pre>
        <audio v-if="audioUrl" ref="audioRef" :src="audioUrl" controls preload="auto" class="audio-player"></audio>
        <button v-if="needsManualPlay" type="button" class="secondary" @click="playAudio">Play Audio</button>
      </section>
    </section>
  </main>
</template>
