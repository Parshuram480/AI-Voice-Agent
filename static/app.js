/**
 * Voice Agent Console — Continuous Conversation Room
 *
 * Handles:
 *  - Continuous microphone streaming via AudioWorklet + WebSocket
 *  - Conversation session lifecycle (start once, auto turn-taking)
 *  - VAD phase tracking (LISTENING → SPEECH_DETECTED → PROCESSING → SPEAKING)
 *  - Barge-in: interrupt TTS when user speaks during playback
 *  - Per-turn STT / LLM / TTS result display
 *  - Latency instrumentation and debug panel
 *  - Text simulation fallback
 */

// ==========================================================================
// DOM Elements
// ==========================================================================
const btnMic = document.getElementById('btn-mic');
const btnEndSession = document.getElementById('btn-end-session');
const btnSessionReset = document.getElementById('btn-session-reset');

const statusBadge = document.getElementById('status-badge');
const stagesContainer = document.getElementById('stages-container');
const resultSection = document.getElementById('result-section');
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

// Phase & Debug elements
const phaseDot = document.getElementById('phase-dot');
const phaseLabel = document.getElementById('phase-label');
const micHint = document.getElementById('mic-hint');
const turnBadge = document.getElementById('turn-badge');

const debugSessionId = document.getElementById('debug-session-id');
const debugPhase = document.getElementById('debug-phase');
const debugTurn = document.getElementById('debug-turn');
const debugVerified = document.getElementById('debug-verified');
const debugState = document.getElementById('debug-state');
const debugLatency = document.getElementById('debug-latency');

// ==========================================================================
// State
// ==========================================================================
let isProcessing = false;
let isSessionActive = false;
let ws = null;
let micAudioContext = null;   // 16kHz for mic capture
let playbackContext = null;    // 24kHz for Gemini audio playback
let micStream = null;
let micSource = null;
let micProcessor = null;
let playbackTime = 0;
let currentPhase = 'IDLE';
let turnCount = 0;
let sessionId = localStorage.getItem('voice_session_id');

// TTS playback queue for barge-in support
let activeSources = [];
let isSpeaking = false;

// ==========================================================================
// Logging
// ==========================================================================
const LOG_TAGS = {
  stt: 'STT',
  llm: 'LLM',
  tts: 'TTS',
  db_lookup: 'DB',
  intent: 'SYS',
  conversation: 'SYS',
  audio_prep: 'SYS',
  error: 'ERR',
  system: 'SYS',
  vad: 'VAD',
  phase: 'PHASE',
};

const LOG_TAG_CLASS = {
  stt: 'log__tag--stt',
  llm: 'log__tag--llm',
  tts: 'log__tag--tts',
  db_lookup: 'log__tag--db',
  db: 'log__tag--db',
  intent: 'log__tag--sys',
  conversation: 'log__tag--sys',
  audio_prep: 'log__tag--sys',
  error: 'log__tag--err',
  system: 'log__tag--sys',
  vad: 'log__tag--vad',
  phase: 'log__tag--phase',
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
// Phase Management
// ==========================================================================
function setPhase(phase) {
  currentPhase = phase;

  // Update phase indicator
  phaseDot.className = 'phase-dot';
  switch (phase) {
    case 'LISTENING':
      phaseDot.classList.add('phase-dot--listening');
      phaseLabel.textContent = '● Listening…';
      micHint.textContent = 'Speak now — silence will finalize your turn';
      btnMic.className = 'mic-room__btn active';
      break;
    case 'SPEECH_DETECTED':
      phaseDot.classList.add('phase-dot--speech');
      phaseLabel.textContent = '● Speech detected';
      micHint.textContent = 'Speaking… pause to send';
      btnMic.className = 'mic-room__btn active';
      break;
    case 'ENDPOINTING':
      phaseDot.classList.add('phase-dot--processing');
      phaseLabel.textContent = '● Finalizing utterance…';
      micHint.textContent = 'Detecting end of speech…';
      btnMic.className = 'mic-room__btn processing';
      break;
    case 'PROCESSING':
      phaseDot.classList.add('phase-dot--processing');
      phaseLabel.textContent = '● Processing…';
      micHint.textContent = 'Transcribing and generating response…';
      btnMic.className = 'mic-room__btn processing';
      break;
    case 'SPEAKING':
      phaseDot.classList.add('phase-dot--speaking');
      phaseLabel.textContent = '● Agent speaking…';
      micHint.textContent = 'Interrupt by speaking to barge in';
      isSpeaking = true;
      btnMic.className = 'mic-room__btn speaking';
      break;
    case 'INTERRUPTED':
      phaseDot.classList.add('phase-dot--speech');
      phaseLabel.textContent = '● Interrupted — listening…';
      micHint.textContent = 'Agent stopped — listening to you';
      btnMic.className = 'mic-room__btn active';
      stopAllPlayback();
      break;
    case 'ENDED':
      phaseDot.classList.add('phase-dot--ended');
      phaseLabel.textContent = '○ Session ended';
      micHint.textContent = 'Click mic to start a new conversation';
      btnMic.className = 'mic-room__btn';
      isSpeaking = false;
      break;
    default:
      phaseLabel.textContent = 'Ready to start';
      micHint.textContent = 'Click to start conversation';
      btnMic.className = 'mic-room__btn';
  }

  // Update debug panel
  debugPhase.textContent = phase;

  addLog('phase', phase);
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
}

function updateMetrics(timings) {
  if (!metricsContainer) return;
  metricsContainer.style.display = 'flex';

  if (timings.is_native) {
    metricStt.textContent = 'N/A';
    metricLlm.textContent = 'N/A';
    metricTts.textContent = 'N/A';
    metricTotal.textContent = 'Native';
    debugLatency.textContent = 'Native Audio (TTFA: N/A)';
    addLog('system', 'Turn latency: Native Audio (TTFA: N/A)');
  } else if (timings.stt_ms !== undefined) {
    // Use pre-computed TTFA precise metrics
    metricStt.textContent = `${timings.stt_ms.toFixed(0)} ms`;
    metricLlm.textContent = `${timings.llm_ms.toFixed(0)} ms`;
    metricTts.textContent = `${timings.tts_first_ms.toFixed(0)} ms`;
    
    // Total is VAD + STT + LLM + TTS First Word
    const totalMs = timings.ttfa_total_ms.toFixed(0);
    metricTotal.textContent = `${totalMs} ms`;
    
    // Add VAD text to debug to be clear
    debugLatency.textContent = `VAD: ${timings.vad_wait_ms.toFixed(0)}ms | Total: ${totalMs} ms (TTFA)`;
    addLog('system', `Turn latency (TTFA): ${totalMs} ms`);

  } else {
    // Fallback for legacy events
    if (timings.stt_duration) {
      metricStt.textContent = `${(timings.stt_duration * 1000).toFixed(0)} ms`;
    } else if (timings.stt_end) {
      metricStt.textContent = `${(timings.stt_end * 1000).toFixed(0)} ms`;
    }

    if (timings.llm_first_token) {
      metricLlm.textContent = `${(timings.llm_first_token * 1000).toFixed(0)} ms`;
    } else if (timings.conversation_duration) {
      metricLlm.textContent = `${(timings.conversation_duration * 1000).toFixed(0)} ms`;
    }

    if (timings.tts_first_audio) {
      metricTts.textContent = `${(timings.tts_first_audio * 1000).toFixed(0)} ms`;
    }

    if (timings.total) {
      const totalMs = (timings.total * 1000).toFixed(0);
      metricTotal.textContent = `${totalMs} ms`;
      debugLatency.textContent = `${totalMs} ms`;
      addLog('system', `Turn latency (end-to-end): ${totalMs} ms`);
    }
  }
}

// ==========================================================================
// Barge-In: Stop all TTS playback
// ==========================================================================
function stopAllPlayback() {
  activeSources.forEach(src => {
    try { src.stop(); } catch (e) { /* already stopped */ }
  });
  activeSources = [];
  playbackTime = 0;
  isSpeaking = false;

  // Notify backend
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: 'barge_in' }));
  }
}

// ==========================================================================
// Continuous Conversation Session
// ==========================================================================
btnMic.addEventListener('click', async () => {
  if (isSessionActive) {
    // If currently speaking, trigger barge-in
    if (isSpeaking) {
      stopAllPlayback();
      addLog('system', 'Barge-in: stopped agent playback');
      return;
    }
    // Otherwise, don't do anything — session is continuous
    return;
  }
  await startSession();
});

btnEndSession.addEventListener('click', () => {
  endSession();
});

btnSessionReset.addEventListener('click', () => {
  resetSession();
});

async function startSession() {
  try {
    // Separate AudioContexts: 16kHz for mic capture, 24kHz for Gemini playback
    micAudioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    playbackContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    await micAudioContext.audioWorklet.addModule('/static/audio-processor.js');

    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true }
    });

    micSource = micAudioContext.createMediaStreamSource(micStream);
    micProcessor = new AudioWorkletNode(micAudioContext, 'pcm-processor');

    // Client-side noise gate: high-pass filter removes low-frequency hum/rumble
    const highPassFilter = micAudioContext.createBiquadFilter();
    highPassFilter.type = 'highpass';
    highPassFilter.frequency.value = 85;  // Cut frequencies below 85Hz (fans, AC, hum)
    highPassFilter.Q.value = 0.7;

    // Gain compensation — ensure filtered audio isn't too quiet
    const gainNode = micAudioContext.createGain();
    gainNode.gain.value = 1.1;

    // Setup WebSocket
    const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    if (!sessionId) {
      sessionId = `mic-${crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(16).slice(2, 10)}`;
      localStorage.setItem('voice_session_id', sessionId);
    }
    const wsUrl = `${wsProto}//${location.host}/ws/mic-stream?session_id=${encodeURIComponent(sessionId)}`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      addLog('system', 'Conversation session started. Speak naturally…');

      // Stream audio continuously through noise filter chain
      micProcessor.port.onmessage = (event) => {
        if (ws && ws.readyState === WebSocket.OPEN && event.data.pcm) {
          ws.send(event.data.pcm);
        }
      };
      // Audio chain: mic → highpass → gain → AudioWorklet → WebSocket
      micSource.connect(highPassFilter);
      highPassFilter.connect(gainNode);
      gainNode.connect(micProcessor);
    };

    ws.onmessage = handleWebSocketMessage;

    ws.onerror = (e) => {
      addLog('error', 'WebSocket error');
      endSession();
    };

    ws.onclose = () => {
      addLog('system', 'WebSocket closed');
      if (isSessionActive) {
        isSessionActive = false;
        setPhase('ENDED');
        setStatus('idle', 'Session ended');
        btnEndSession.disabled = true;
      }
    };

    // UI Updates
    isSessionActive = true;
    turnCount = 0;
    resetStages();
    resetResults();
    resultTranscript.textContent = '';
    resultReply.textContent = '';
    playbackTime = 0;

    btnEndSession.disabled = false;
    setStatus('active', 'Active Session');
    setPhase('LISTENING');
    turnBadge.textContent = 'Turn 0';
    debugTurn.textContent = '0';

  } catch (err) {
    addLog('error', `Mic error: ${err.message}`);
    setStatus('error', 'Mic Error');
  }
}

function endSession() {
  if (!isSessionActive) return;

  isSessionActive = false;
  isSpeaking = false;
  stopAllPlayback();

  if (micSource) micSource.disconnect();
  if (micProcessor) micProcessor.disconnect();
  if (micStream) micStream.getTracks().forEach(t => t.stop());

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: 'end_session' }));
  }

  setPhase('ENDED');
  setStatus('idle', 'Session ended');
  btnEndSession.disabled = true;

  addLog('system', `Session ended after ${turnCount} turns.`);
}

function resetSession() {
  endSession();

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.close();
  }
  ws = null;
  sessionId = null;
  localStorage.removeItem('voice_session_id');
  turnCount = 0;

  resetResults();
  resetStages();
  setStatus('idle', 'Idle');
  setPhase('IDLE');
  turnBadge.textContent = 'Turn 0';
  debugSessionId.textContent = '—';
  debugTurn.textContent = '0';
  debugPhase.textContent = 'IDLE';
  debugVerified.textContent = 'No';
  debugState.textContent = '—';
  debugLatency.textContent = '—';

  addLog('system', 'Session reset. Click mic to start a new conversation.');
}

// ==========================================================================
// WebSocket Message Handler
// ==========================================================================
async function handleWebSocketMessage(event) {
  try {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case 'phase':
        setPhase(data.phase);

        // When we transition to PROCESSING, reset result fields for new turn
        if (data.phase === 'PROCESSING' || data.phase === 'SPEECH_DETECTED') {
          resetStages();
          resultTranscript.textContent = '';
          resultReply.textContent = '';
          if (metricsContainer) metricsContainer.style.display = 'none';
        }

        // Playback scheduler continues gaplessly without resetting on SPEAKING.

        // When listening resumes, mark speaking done
        if (data.phase === 'LISTENING' && isSpeaking) {
          isSpeaking = false;
        }
        break;

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
        try {
          if (!playbackContext) break;
          const arrayBuffer = base64ToArrayBuffer(data.data);
          
          if (data.format === 'wav' || data.format === 'mp3') {
             // Let the browser decode full WAV/MP3 files natively
             const audioBuffer = await playbackContext.decodeAudioData(arrayBuffer);
             playAudioChunk(audioBuffer);
          } else {
             // Raw PCM parsing (Gemini or Cartesia sub-second chunks without headers)
             let pcm16Buffer = arrayBuffer;
             if (pcm16Buffer.byteLength % 2 !== 0) {
               pcm16Buffer = pcm16Buffer.slice(0, pcm16Buffer.byteLength - 1);
             }
             if (pcm16Buffer.byteLength === 0) break;
             const pcm16 = new Int16Array(pcm16Buffer);
             const sampleRate = data.sampleRate || 24000;
             const audioBuffer = playbackContext.createBuffer(1, pcm16.length, sampleRate);
             const channelData = audioBuffer.getChannelData(0);
             for (let i = 0; i < pcm16.length; i++) {
               channelData[i] = pcm16[i] / 32768.0; // Convert Int16 to Float32
             }
             playAudioChunk(audioBuffer);
          }
        } catch (e) {
          console.error('Failed to play TTS chunk', e);
        }
        break;

      case 'timing':
        updateMetrics(data.timings);
        break;

      case 'turn_done':
        turnCount++;
        turnBadge.textContent = `Turn ${turnCount}`;
        debugTurn.textContent = `${turnCount}`;

        const r = data.result;
        if (r) {
          resultIntent.textContent = r.intent || '—';
          debugState.textContent = r.state || '—';
          debugVerified.textContent = r.verified ? 'Yes' : 'No';

          if (r.customer) {
            resultCustomer.textContent = `${r.customer.full_name} (DOB: ${r.customer.date_of_birth})`;
          } else {
            resultCustomer.textContent = '—';
          }

          if (r.orders && r.orders.length > 0) {
            resultOrder.innerHTML = r.orders.map(o => `#${o.order_number} — ${o.status}`).join('<br>');
          } else {
            resultOrder.textContent = '—';
          }

          if (r.input_audio_url) {
            inputAudioPlayer.src = r.input_audio_url;
            inputAudioPlayer.style.display = 'block';
          }

          if (r.reply_text) {
            resultReply.textContent = r.reply_text;
          }
        }

        addLog('system', `Turn ${turnCount} complete`);
        break;

      case 'session':
        if (data.session_id) {
          sessionId = data.session_id;
          localStorage.setItem('voice_session_id', sessionId);
          debugSessionId.textContent = sessionId;
          addLog('system', `Session: ${sessionId}`);
        }
        break;

      case 'session_end':
        addLog('system', `Session ended — total turns: ${data.total_turns}`);
        setPhase('ENDED');
        setStatus('idle', 'Session ended');
        isSessionActive = false;
        btnEndSession.disabled = true;
        break;
    }
  } catch (e) {
    console.error("Failed to parse WS message", e);
  }
}

// ==========================================================================
// Progressive Audio Playback with Barge-In Support
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
  if (!playbackContext) return;

  const source = playbackContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(playbackContext.destination);

  // Schedule gapless playback
  const currentTime = playbackContext.currentTime;
  // Only reset if playbackTime is completely behind currentTime
  if (playbackTime < currentTime) {
    playbackTime = currentTime + 0.05; // 50ms jitter buffer for network lag
  }

  source.start(playbackTime);
  playbackTime += audioBuffer.duration;

  // Track active source for barge-in
  activeSources.push(source);
  source.onended = () => {
    activeSources = activeSources.filter(s => s !== source);
  };
}



addLog('system', 'Voice Agent Conversation Room ready. Click the microphone to start.');
