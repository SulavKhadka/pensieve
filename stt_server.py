from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from faster_whisper import WhisperModel
import numpy as np
from pydub import AudioSegment
import io

app = FastAPI()

model_size = "distil-large-v2"
model = WhisperModel(model_size, device="cuda", compute_type="float16")
sample_rate = 16000
chunk_ms = 500
capture_duration_secs = 5

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Audio Streaming</title>
    </head>
    <body>
        <h1>WebSocket Audio Streaming</h1>
        <button id="startButton">Start Streaming</button>
        <button id="stopButton" disabled>Stop Streaming</button>
        <ul id='messages'></ul>
        <script>
            let ws;
            let mediaRecorder;
            let audioChunks = [];
            const startButton = document.getElementById('startButton');
            const stopButton = document.getElementById('stopButton');

            startButton.onclick = startStreaming;
            stopButton.onclick = stopStreaming;

            function startStreaming() {
                ws = new WebSocket("ws://localhost:8000/ws");
                ws.onmessage = function(event) {
                    var messages = document.getElementById('messages')
                    var message = document.createElement('li')
                    var content = document.createTextNode(event.data)
                    message.appendChild(content)
                    messages.appendChild(message)
                };

                navigator.mediaDevices.getUserMedia({ audio: true })
                    .then(stream => {
                        // Create audio context with lower sample rate (most browsers use 44100Hz or 48000Hz by default)
                        const audioContext = new AudioContext();
                        const source = audioContext.createMediaStreamSource(stream);
                        
                        // Create processor with desired chunk size (4096 samples)
                        const processor = audioContext.createScriptProcessor(4096, 1, 1);
                        
                        // Create a resampler to convert to 16000Hz
                        // We need to use a resampler because browsers typically don't support 16000Hz directly
                        const resampleRatio = 16000 / audioContext.sampleRate;
                        
                        source.connect(processor);
                        processor.connect(audioContext.destination);
                        
                        processor.onaudioprocess = function(e) {
                            // Get original audio data
                            const inputData = e.inputBuffer.getChannelData(0);
                            
                            // Perform simple resampling (more sophisticated resampling might be needed for production)
                            const resampledLength = Math.floor(inputData.length * resampleRatio);
                            const resampledData = new Float32Array(resampledLength);
                            
                            for (let i = 0; i < resampledLength; i++) {
                                // Linear interpolation for simple downsampling
                                const idx = i / resampleRatio;
                                const idx1 = Math.floor(idx);
                                const idx2 = Math.min(idx1 + 1, inputData.length - 1);
                                const frac = idx - idx1;
                                
                                resampledData[i] = inputData[idx1] * (1 - frac) + inputData[idx2] * frac;
                            }
                            
                            if (ws.readyState === WebSocket.OPEN) {
                                ws.send(resampledData.buffer);
                            }
                        };
                    });

                startButton.disabled = true;
                stopButton.disabled = false;
            }

            function stopStreaming() {
                mediaRecorder.stop();
                ws.close();
                startButton.disabled = false;
                stopButton.disabled = true;
            }
        </script>
    </body>
</html>
"""


@app.get("/")
async def get():
    return HTMLResponse(html)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    sample_rate = 16000
    
    # Buffer to accumulate audio samples
    audio_buffer = np.array([], dtype=np.float32)
    
    # How many samples constitute 5 seconds of audio
    samples_for_5sec = 2 * sample_rate
    
    while True:
        try:
            data = await websocket.receive_bytes()
            if not data:
                continue
                
            chunk = np.frombuffer(data, dtype=np.float32)
            
            # Add to buffer
            audio_buffer = np.append(audio_buffer, chunk)
            
            # Process if we have enough data
            if len(audio_buffer) >= samples_for_5sec:
                # Transcribe
                segments, info = model.transcribe(audio_buffer, beam_size=5, language="en")
                
                # Get transcription text\
                for segment in segments:
                    print(segment)
                transcription = " ".join([segment.text for segment in segments])
                
                if transcription.strip():
                    await websocket.send_text(transcription)
                
                # Reset buffer (optionally keep some overlap)
                audio_buffer = audio_buffer[samples_for_5sec:]
                
        except Exception as e:
            print(f"WebSocket error: {e}")
            break