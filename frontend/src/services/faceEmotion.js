// In-browser face detection + emotion recognition.
//
// Everything runs on the student's machine with @vladmandic/face-api
// (MIT licence). Model weights are served from /models, which is part of the
// built frontend, so this works offline and no camera frame ever leaves the
// browser: only the resulting label + confidence is sent to the API.

const MODEL_URL = '/models'

// face-api is ~1.3 MB, so it is loaded on demand instead of on page load.
let faceapi = null
async function getFaceApi() {
  if (!faceapi) faceapi = await import('@vladmandic/face-api')
  return faceapi
}

export const EMOTIONS = ['neutral', 'happy', 'sad', 'angry', 'fear', 'disgust', 'surprise']

// face-api uses slightly different ids for two emotions.
const LABEL_MAP = {
  neutral: 'neutral',
  happy: 'happy',
  sad: 'sad',
  angry: 'angry',
  fearful: 'fear',
  disgusted: 'disgust',
  surprised: 'surprise',
}

let loadingPromise = null

async function loadFaceApi() {
  if (!loadingPromise) {
    loadingPromise = getFaceApi()
      .then((lib) => Promise.all([
        lib.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
        lib.nets.faceExpressionNet.loadFromUri(MODEL_URL),
      ]).then(() => lib))
      .catch((err) => {
        loadingPromise = null
        throw err
      })
  }
  return loadingPromise
}

export function loadFaceModels() {
  return loadFaceApi()
}

const brightnessCanvas = typeof document !== 'undefined' ? document.createElement('canvas') : null
brightnessCanvas && (brightnessCanvas.width = 64)
brightnessCanvas && (brightnessCanvas.height = 48)

/** Mean luma of the current frame (0-255). Used to say "too dark" instead of
 *  guessing an emotion from a black rectangle. */
export function frameBrightness(video) {
  if (!video || !brightnessCanvas || video.readyState < 2) return null
  const ctx = brightnessCanvas.getContext('2d', { willReadFrequently: true })
  try {
    ctx.drawImage(video, 0, 0, brightnessCanvas.width, brightnessCanvas.height)
    const { data } = ctx.getImageData(0, 0, brightnessCanvas.width, brightnessCanvas.height)
    let sum = 0
    for (let i = 0; i < data.length; i += 4) {
      sum += 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2]
    }
    return sum / (data.length / 4)
  } catch {
    return null
  }
}

/**
 * Analyse one frame.
 * Returns { status: 'no_face' | 'too_dark' | 'result', emotion, confidence,
 *           top3: [{emotion, confidence}], box }
 */
export async function analyseFrame(video) {
  const lib = await loadFaceApi()
  if (!video || video.readyState < 2 || !video.videoWidth) {
    return { status: 'starting' }
  }

  const options = new lib.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.35 })
  const brightness = frameBrightness(video)
  const result = await lib.detectSingleFace(video, options).withFaceExpressions()
  const tooDark = brightness !== null && brightness < 45

  if (!result) {
    return { status: tooDark ? 'too_dark' : 'no_face', brightness }
  }

  const entries = Object.entries(result.expressions || {})
    .map(([label, value]) => [LABEL_MAP[label] || label, Number(value) || 0])
    .filter(([label]) => EMOTIONS.includes(label))
    .sort((a, b) => b[1] - a[1])

  if (!entries.length) return { status: 'no_face', brightness }

  return {
    status: 'result',
    emotion: entries[0][0],
    confidence: entries[0][1],
    top3: entries.slice(0, 3).map(([emotion, confidence]) => ({ emotion, confidence })),
    box: result.detection?.box,
    brightness,
  }
}

/** Average the last N frames so one noisy frame cannot flip the label. */
export function smoothEmotion(history, frame, windowSize = 5) {
  if (!frame || frame.status !== 'result') return { history: [], frame }
  const vector = {}
  frame.top3.forEach((item) => { vector[item.emotion] = item.confidence })
  const nextHistory = [...history, vector].slice(-windowSize)
  const average = {}
  nextHistory.forEach((v) => {
    Object.entries(v).forEach(([key, value]) => {
      average[key] = (average[key] || 0) + value / nextHistory.length
    })
  })
  const sorted = Object.entries(average).sort((a, b) => b[1] - a[1])
  const [emotion, confidence] = sorted[0] || [frame.emotion, frame.confidence]
  const runnerUp = sorted[1]?.[1] || 0
  const uncertain = confidence < 0.45 || confidence - runnerUp < 0.08
  return {
    history: nextHistory,
    frame: {
      ...frame,
      emotion: uncertain ? 'uncertain' : emotion,
      rawEmotion: emotion,
      confidence,
      top3: sorted.slice(0, 3).map(([label, value]) => ({ emotion: label, confidence: value })),
      uncertain,
      smoothed: true,
    },
  }
}

/** Plain-language mapping of getUserMedia failures. */
export function cameraErrorMessage(err) {
  const name = err?.name || ''
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') {
    return { kind: 'denied', message: 'Camera permission was denied. Allow camera access in your browser settings (the padlock in the address bar), then press Retry camera.' }
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError' || name === 'OverconstrainedError') {
    return { kind: 'unavailable', message: 'No camera was found. Connect a webcam and press Retry camera.' }
  }
  if (name === 'NotReadableError' || name === 'TrackStartError' || name === 'AbortError') {
    return { kind: 'in_use', message: 'The camera is already in use by another app or browser tab. Close it and press Retry camera.' }
  }
  return { kind: 'unknown', message: err?.message || 'The camera could not be started.' }
}
