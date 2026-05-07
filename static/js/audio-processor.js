const BUFFER_SIZE = 2048; // 128ms at 16kHz — reduces WS message frequency ~16x

class AudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buf = new Float32Array(BUFFER_SIZE);
    this._pos = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input.length) return true;
    const src = input[0];

    for (let i = 0; i < src.length; i++) {
      this._buf[this._pos++] = src[i];
      if (this._pos === BUFFER_SIZE) {
        const pcm = new Int16Array(BUFFER_SIZE);
        for (let j = 0; j < BUFFER_SIZE; j++) {
          const s = Math.max(-1, Math.min(1, this._buf[j]));
          pcm[j] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        this.port.postMessage(pcm.buffer, [pcm.buffer]);
        this._buf = new Float32Array(BUFFER_SIZE);
        this._pos = 0;
      }
    }
    return true;
  }
}

registerProcessor('audio-processor', AudioProcessor);
