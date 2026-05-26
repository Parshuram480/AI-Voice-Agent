/**
 * Voice Agent Console — Frontend Logic (Streaming Pipeline)
 *
 * Handles:
 *  - Simulate form submission (text → /api/simulate)
 *  - Microphone streaming (AudioWorklet + WebSocket → /ws/mic-stream)
 *  - Progressive STT / LLM updates
 *  - Chunked TTS playback via Web Audio API
 *  - Latency instrumentation display
 */

// ==========================================================================
// DOM Elements
// ==========================================================================
const form = document.getElementById('simulate-form');
const btnSend = document.getElementById('btn-send');
const btnClear = document.getElementById('btn-clear');
const btnMic = document.getElementById('btn-mic');

const inputName = document.getElementById('input-name');
const inputDob = document.getElementById('input-dob');
const inputQuery = document.getElementById('input-query');

const statusBadge = document.getElementById('status-badge');
const stagesContainer = document.getElementById('stages-container');
const resultSection = document.getElementById('result-section');
const audioSection = document.getElementById('audio-section');
const audioPlayer = document.getElementById('audio-player');
const waveformCanvas = document.getElementById('waveform-canvas');
const logContainer = document.getElementById('log-container');

const resultTranscript = document.getElementById('result-transcript');
const inputAudioPlayer = document.getElementById('input-audio-player');
const resultIntent = document.getElementById('result-intent');
const resultCustomer = document.getElementById('result-customer');
const resultOrder = document.getElementById('result-order');
const resultReply = document.getElementById('result-reply');

const metricsContainer = document.getElementById('metrics-container');
const metricStt = document.getElementById('metric-stt');
const metricLlm = document.getElementById('metric-llm');
const metricTts = document.getElementById('metric-tts');
const metricTotal = document.getElementById('metric-total');

// ==========================================================================
// State
// ==========================================================================
let isProcessing = false;
let isRecording = false;
let ws = null;
let audioContext = null;
let micStream = null;
let micSource = null;
let micProcessor = null;
let playbackTime = 0; // for scheduling chunks gaplessly
let micStopTimestamp = null;

// ==========================================================================
// Logging
// ==========================================================================
const LOG_TAGS = {
  stt: 'STT',
  llm: 'LLM',
  tts: 'TTS',
  db_lookup: 'DB',
  intent: 'SYS',
  audio_prep: 'SYS',
  error: 'ERR',
  system: 'SYS',
};

const LOG_TAG_CLASS = {
  stt: 'log__tag--stt',
  llm: 'log__tag--llm',
  tts: 'log__tag--tts',
  db_lookup: 'log__tag--db',
  db: 'log__tag--db',
  intent: 'log__tag--sys',
  audio_prep: 'log__tag--sys',
  error: 'log__tag--err',
  system: 'log__tag--sys',
};

function clearLog() {
  logContainer.innerHTML = '';
}

function addLog(tag, message) {
  const empty = logContainer.querySelector('.log__empty');
  if (empty) empty.remove();

  const now = new Date().toLocaleTimeString('en-US', { hour12: false });
  const entry = document.createElement('div');
  entry.className = 'log__entry';

  const tagKey = tag.toLowerCase().replace(/\s+/g, '_');
  const tagClass = LOG_TAG_CLASS[tagKey] || 'log__tag--sys';
  const tagLabel = LOG_TAGS[tagKey] || tag.toUpperCase();

  entry.innerHTML = `
    <span class="log__time">${now}</span>
    <span class="log__tag ${tagClass}">${tagLabel}</span>
    <span class="log__msg">${escapeHtml(message)}</span>
  `;
  logContainer.appendChild(entry);
  logContainer.scrollTop = logContainer.scrollHeight;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ==========================================================================
// Status & Stages
// ==========================================================================
function setStatus(status, label) {
  statusBadge.className = `status-badge status-badge--${status}`;
  statusBadge.innerHTML = `<span class="stage__dot"></span> ${label}`;
}

function resetStages() {
  document.querySelectorAll('.stage').forEach(el => {
    el.className = 'stage';
  });
}

function updateStage(stageName, status) {
  const el = document.querySelector(`.stage[data-stage="${stageName}"]`);
  if (el) {
    el.className = `stage stage--${status}`;
  }
}

function animateStages(stages) {
  resetStages();
  if (!stages || !stages.length) return;
  stages.forEach(s => updateStage(s.stage, s.status));
}

// ==========================================================================
// Results & Metrics
// ==========================================================================
function resetResults() {
  resultTranscript.textContent = '—';
  resultIntent.textContent = '—';
  resultCustomer.textContent = '—';
  resultOrder.textContent = '—';
  resultReply.textContent = '—';
  inputAudioPlayer.style.display = 'none';
  if (metricsContainer) metricsContainer.style.display = 'none';
  resultSection.style.display = 'block';
}

function updateMetrics(timings) {
  if (!metricsContainer) return;
  metricsContainer.style.display = 'flex';
  
  if (timings.stt_early_end) {
    metricStt.textContent = `${(timings.stt_early_end * 1000).toFixed(0)} ms`;
  } else if (timings.stt_final_end) {
    metricStt.textContent = `${(timings.stt_final_end * 1000).toFixed(0)} ms`;
  }
  
  if (timings.llm_first_token) {
    metricLlm.textContent = `${(timings.llm_first_token * 1000).toFixed(0)} ms`;
  }
  
  if (timings.tts_first_audio) {
    metricTts.textContent = `${(timings.tts_first_audio * 1000).toFixed(0)} ms`;
  }
  
  if (timings.total) {
    const totalMs = (timings.total * 1000).toFixed(0);
    metricTotal.textContent = `${totalMs} ms`;
    addLog('system', `Latency (total end-to-end): ${totalMs} ms`);
  }
}

// ==========================================================================
// Streaming Microphone Flow (WebSocket)
// ==========================================================================
btnMic.addEventListener('click', async () => {
  if (isRecording) {
    stopRecording();
  } else {
    await startRecording();
  }
});

async function startRecording() {
  try {
    // Setup AudioContext & AudioWorklet
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    await audioContext.audioWorklet.addModule('/static/audio-processor.js');

    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true }
    });

    micSource = audioContext.createMediaStreamSource(micStream);
    micProcessor = new AudioWorkletNode(audioContext, 'pcm-processor');

    // Setup WebSocket
    const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${wsProto}//${location.host}/ws/mic-stream`);
    
    ws.onopen = () => {
      addLog('system', 'Streaming WebSocket connected. Speak now...');
      
      // Send audio frames from Worklet to WS
      micProcessor.port.onmessage = (event) => {
        if (ws && ws.readyState === WebSocket.OPEN && event.data.pcm) {
          ws.send(event.data.pcm); // Send raw binary PCM
        }
      };
      micSource.connect(micProcessor);
    };

    ws.onmessage = handleWebSocketMessage;
    
    ws.onerror = (e) => {
      addLog('error', 'WebSocket error');
      stopRecording();
    };
    
    ws.onclose = () => {
      addLog('system', 'WebSocket closed');
    };

    // UI Updates
    isRecording = true;
    btnMic.classList.add('recording');
    setStatus('processing', 'Recording & Streaming...');
    resetStages();
    resetResults();
    resultTranscript.textContent = '';
    resultReply.textContent = '';
    playbackTime = 0; // reset playback scheduler
    
  } catch (err) {
    addLog('error', `Mic error: ${err.message}`);
    setStatus('error', 'Mic Error');
  }
}

function stopRecording() {
  isRecording = false;
  btnMic.classList.remove('recording');
  setStatus('processing', 'Processing...');
  
  micStopTimestamp = performance.now();
  
  if (micSource) micSource.disconnect();
  if (micProcessor) micProcessor.disconnect();
  if (micStream) micStream.getTracks().forEach(t => t.stop());
  
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: 'stop' }));
  }
}

async function handleWebSocketMessage(event) {
  try {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case 'stage':
        addLog(data.stage, `[${data.status.toUpperCase()}] ${data.detail}`);
        updateStage(data.stage, data.status);
        break;
        
      case 'stt':
        resultTranscript.textContent = data.text;
        break;
        
      case 'llm_token':
        resultReply.textContent += data.token;
        break;
        
      case 'tts_audio':
        // Decode base64 WAV chunk and play it via AudioContext
        const arrayBuffer = base64ToArrayBuffer(data.data);
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
        playAudioChunk(audioBuffer);
        break;
        
      case 'timing':
        updateMetrics(data.timings);
        break;
        
      case 'done':
        setStatus('success', 'Complete');
        // Update final data fields
        const r = data.result;
        resultIntent.textContent = r.intent || '—';
        if (r.customer) {
          resultCustomer.textContent = `${r.customer.full_name} (DOB: ${r.customer.date_of_birth})`;
        } else {
          resultCustomer.textContent = 'Not found';
        }
        if (r.orders && r.orders.length > 0) {
          resultOrder.innerHTML = r.orders.map(o => `#${o.order_number} — ${o.status}`).join('<br>');
        } else {
          resultOrder.textContent = 'No orders found';
        }
        if (r.input_audio_url) {
          inputAudioPlayer.src = r.input_audio_url;
          inputAudioPlayer.style.display = 'block';
        }
        break;
    }
  } catch (e) {
    console.error("Failed to parse WS message", e);
  }
}

// ==========================================================================
// Progressive Audio Playback
// ==========================================================================
function base64ToArrayBuffer(base64) {
  const binary_string = window.atob(base64);
  const len = binary_string.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binary_string.charCodeAt(i);
  }
  return bytes.buffer;
}

function playAudioChunk(audioBuffer) {
  if (!audioContext) return;
  
  const source = audioContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioContext.destination);
  
  // Schedule gapless playback
  const currentTime = audioContext.currentTime;
  if (playbackTime < currentTime) {
    playbackTime = currentTime;
  }
  
  source.start(playbackTime);
  playbackTime += audioBuffer.duration;

  if (micStopTimestamp !== null) {
    const latencyMs = Math.max(0, performance.now() - micStopTimestamp);
    const latencySec = (latencyMs / 1000).toFixed(2);
    addLog('system', `Latency (mic stop → playback): ${Math.round(latencyMs)} ms (${latencySec}s)`);
    micStopTimestamp = null;
  }
}

// ==========================================================================
// Simulate Form Submission (Fallback / Text Simulation)
// ==========================================================================
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (isProcessing) return;

  const name = inputName.value.trim();
  const dob = inputDob.value.trim();
  const query = inputQuery.value.trim();

  if (!name || !dob || !query) {
    addLog('error', 'Please fill in all fields.');
    return;
  }

  isProcessing = true;
  btnSend.disabled = true;
  resetStages();
  resetResults();
  if (metricsContainer) metricsContainer.style.display = 'none';
  setStatus('processing', 'Processing...');
  addLog('system', `Query: "${query}" | Customer: ${name} (${dob})`);

  try {
    const res = await fetch('/api/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, dob, query }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Server error: ${res.status}`);
    }

    const data = await res.json();
    if (data.stages) animateStages(data.stages);

    resultTranscript.textContent = data.transcript || '—';
    resultIntent.textContent = data.intent || '—';
    resultReply.textContent = data.reply_text || '—';
    
    if (data.customer) {
      resultCustomer.textContent = `${data.customer.full_name} (DOB: ${data.customer.date_of_birth})`;
    }
    if (data.orders && data.orders.length > 0) {
      resultOrder.innerHTML = data.orders.map(o => `#${o.order_number} — ${o.status}`).join('<br>');
    }
    
    if (data.timings) updateMetrics(data.timings);

    if (data.audio_url) {
      audioSection.style.display = 'block';
      audioPlayer.src = data.audio_url;
      audioPlayer.play().catch(e => console.warn(e));
    }

    setStatus('success', 'Complete');
  } catch (err) {
    addLog('error', err.message);
    setStatus('error', 'Error');
  } finally {
    isProcessing = false;
    btnSend.disabled = false;
  }
});

btnClear.addEventListener('click', () => {
  inputName.value = '';
  inputDob.value = '';
  inputQuery.value = '';
  resetResults();
  resetStages();
  setStatus('idle', 'Idle');
  clearLog();
  audioSection.style.display = 'none';
});

addLog('system', 'Voice Agent Console ready (Streaming Mode). Click mic to start streaming audio.');
