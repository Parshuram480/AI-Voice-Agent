/**
 * AudioWorkletProcessor for capturing raw PCM audio in the browser.
 * 
 * Captures audio from the microphone, optionally downsamples it
 * to 16kHz, and posts the raw 16-bit PCM buffer to the main thread.
 */

class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 4096;
    this.buffer = new Float32Array(this.bufferSize);
    this.bufferIndex = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input.length > 0) {
      const channelData = input[0]; // Mono channel

      for (let i = 0; i < channelData.length; i++) {
        this.buffer[this.bufferIndex++] = channelData[i];

        if (this.bufferIndex >= this.bufferSize) {
          this.flush();
          this.bufferIndex = 0;
        }
      }
    }
    return true; // Keep processor alive
  }

  flush() {
    // We send Float32 arrays to the main thread, which can handle the
    // downsampling and conversion to 16-bit Int if needed.
    // However, it's more efficient to do the Float32 -> Int16 conversion here.
    
    const int16Buffer = new Int16Array(this.bufferSize);
    for (let i = 0; i < this.bufferSize; i++) {
      let s = Math.max(-1, Math.min(1, this.buffer[i]));
      int16Buffer[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    
    // Post the raw 16-bit PCM chunk to the main thread
    this.port.postMessage({ pcm: int16Buffer.buffer }, [int16Buffer.buffer]);
  }
}

registerProcessor('pcm-processor', PCMProcessor);
