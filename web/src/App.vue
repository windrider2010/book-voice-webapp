<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

import arendellePhoto from './assets/themes/arendelle-harbor.jpg'
import frozenPhoto from './assets/themes/frozen-ice-cave.jpg'
import moanaPhoto from './assets/themes/moana-outrigger.jpg'
import { submitReadRequest, type ReadJobProgressPayload } from './lib/api'
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
  photo: string
  photoAlt: string
}

const themes: ThemeOption[] = [
  {
    id: 'frozen',
    label: 'Frozen',
    hint: 'Ice cave',
    eyebrow: 'Frozen Capture',
    title: 'Give the page a tall, full-frame ice window.',
    lede: 'The camera stage now opens edge to edge so one page can dominate the preview before you capture it.',
    resultTag: 'ice-tuned layout',
    photo: frozenPhoto,
    photoAlt: 'Blue glacial ice cave with reflected light',
  },
  {
    id: 'arendelle',
    label: 'Arendelle',
    hint: 'Fjord harbor',
    eyebrow: 'Arendelle Library',
    title: 'Keep the header tighter and the reading deck calmer.',
    lede: 'A compact top section leaves more room for the live camera while the theme swaps to a real harbor image instead of a tint only.',
    resultTag: 'kingdom mode',
    photo: arendellePhoto,
    photoAlt: 'Nordic harbor town beside a fjord',
  },
  {
    id: 'moana',
    label: 'Moana',
    hint: 'Ocean canoe',
    eyebrow: 'Open Ocean',
    title: 'Use a brighter ocean frame with a taller mobile camera box.',
    lede: 'The phone gets a taller capture stage on small screens, which keeps the full page easier to line up outdoors or on the move.',
    resultTag: 'voyager mode',
    photo: moanaPhoto,
    photoAlt: 'Outrigger canoe on blue tropical water near the shore',
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
const statusMessage = ref('Open the camera and fill the tall frame with one page.')
const errorMessage = ref('')
const recognizedText = ref('')
const audioUrl = ref('')
const needsManualPlay = ref(false)
const paragraphsTotal = ref(0)
const paragraphsCompleted = ref(0)

const activeTheme = computed<ThemeOption>(() => themes.find((theme) => theme.id === themeId.value) ?? defaultTheme)
const canCapture = computed(() => cameraReady.value && !isSubmitting.value)
const resultTag = computed(() => {
  if (isSubmitting.value && paragraphsTotal.value > 0) {
    return `audio ${paragraphsCompleted.value}/${paragraphsTotal.value}`
  }
  if (isSubmitting.value && recognizedText.value) {
    return 'ocr ready'
  }
  return activeTheme.value.resultTag
})
const processingTitle = computed(() => {
  if (paragraphsTotal.value > 0) {
    return paragraphsCompleted.value < paragraphsTotal.value
      ? `Building audio ${paragraphsCompleted.value}/${paragraphsTotal.value}`
      : 'Finalizing audio'
  }
  if (recognizedText.value) {
    return 'OCR ready'
  }
  return 'Reading the page...'
})

function selectTheme(id: ThemeId): void {
  themeId.value = id
}

function getThemeArtStyle(photo: string): { backgroundImage: string } {
  return {
    backgroundImage: `linear-gradient(180deg, rgba(4, 10, 18, 0.18), rgba(4, 10, 18, 0.82)), url(${photo})`,
  }
}

function stopStream(): void {
  streamRef.value?.getTracks().forEach((track) => track.stop())
  streamRef.value = null
}

function applyReadProgress(progress: ReadJobProgressPayload): void {
  if (progress.text) {
    recognizedText.value = progress.text
  }
  paragraphsTotal.value = progress.paragraphs_total
  paragraphsCompleted.value = progress.paragraphs_completed

  if (progress.status === 'queued') {
    statusMessage.value = 'Image uploaded. Waiting for the reader queue...'
    return
  }

  if (progress.stage === 'ocr') {
    statusMessage.value = 'Image uploaded. OCR is reading the page...'
    return
  }

  if (progress.stage === 'tts') {
    if (progress.paragraphs_total > 0) {
      if (progress.paragraphs_completed === 0) {
        statusMessage.value = `OCR ready. Building audio paragraph 1 of ${progress.paragraphs_total}...`
      } else if (progress.paragraphs_completed < progress.paragraphs_total) {
        statusMessage.value = `OCR ready. Built ${progress.paragraphs_completed} of ${progress.paragraphs_total} audio paragraphs...`
      } else {
        statusMessage.value = 'OCR ready. Finalizing audio...'
      }
    } else {
      statusMessage.value = 'OCR ready. Building audio...'
    }
  }
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
    statusMessage.value = 'Camera ready. Fill most of the tall frame with the page, then capture.'
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
  recognizedText.value = ''
  audioUrl.value = ''
  paragraphsTotal.value = 0
  paragraphsCompleted.value = 0
  statusMessage.value = 'Uploading the visible frame for OCR...'
  needsManualPlay.value = false

  try {
    const blob = await captureVideoFrame(videoRef.value)
    const payload = await submitReadRequest(blob, 'bilingual', applyReadProgress)
    recognizedText.value = payload.text
    audioUrl.value = payload.audio_url
    paragraphsCompleted.value = paragraphsTotal.value || paragraphsCompleted.value
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
          <p class="brand-mark">Book Voice</p>
          <p class="brand-subtitle">Snap a page, run OCR, and play it back without wasting the screen on oversized chrome.</p>
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
            :style="getThemeArtStyle(theme.photo)"
            @click="selectTheme(theme.id)"
          >
            <span class="theme-pill__name">{{ theme.label }}</span>
            <span class="theme-pill__hint">{{ theme.hint }}</span>
          </button>
        </div>
      </header>

      <section class="hero">
        <div class="hero-copy">
          <p class="eyebrow">{{ activeTheme.eyebrow }}</p>
          <h1>{{ activeTheme.title }}</h1>
          <p class="lede">{{ activeTheme.lede }}</p>
        </div>
        <div class="hero-art">
          <img :src="activeTheme.photo" :alt="activeTheme.photoAlt" />
        </div>
      </section>

      <section class="camera-stage">
        <div class="camera-card">
          <div class="camera-backdrop" :style="getThemeArtStyle(activeTheme.photo)" aria-hidden="true"></div>
          <video ref="videoRef" autoplay muted playsinline class="preview" :class="{ live: cameraReady }" />
          <div class="camera-overlay">
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
                <p class="processing-title">{{ processingTitle }}</p>
                <p>{{ statusMessage }}</p>
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
          <span>{{ resultTag }}</span>
        </div>
        <pre class="text-preview">{{ recognizedText }}</pre>
        <p v-if="isSubmitting && !audioUrl" class="result-note">
          Audio is still rendering. {{ paragraphsCompleted }}/{{ paragraphsTotal || '?' }} paragraphs complete.
        </p>
        <audio v-if="audioUrl" ref="audioRef" :src="audioUrl" controls preload="auto" class="audio-player"></audio>
        <button v-if="needsManualPlay" type="button" class="secondary" @click="playAudio">Play Audio</button>
      </section>
    </section>
  </main>
</template>
