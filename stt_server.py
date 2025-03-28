from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from whisper_streamer.whisper_online import *
import json
import numpy as np
import time
import openai
from fastapi.middleware.cors import CORSMiddleware
from secret_keys import OPENROUTER_KEY
from report_generator import generate_report_from_outline, outline_report
import os
import base64
import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.status import HTTP_401_UNAUTHORIZED

# Authentication configuration
# These should be set as environment variables in production
APP_USERNAME = os.environ.get("APP_USERNAME", "user")
APP_PASSWORD = os.environ.get("APP_PASSWORD", secrets.token_urlsafe(16))  # Generates a secure random password if not set

# If password is auto-generated, print it to console (for development only)
if os.environ.get("APP_PASSWORD") is None:
    print("====== SECURITY NOTICE ======")
    print("Auto-generated credentials for application access:")
    print(f"Username: {APP_USERNAME}")
    print(f"Password: {APP_PASSWORD}")
    print("Set APP_USERNAME and APP_PASSWORD environment variables to use custom credentials.")
    print("==============================")

# Custom middleware for HTTP Basic Authentication
class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Check if the Authorization header is present
        auth_header = request.headers.get("Authorization")
        
        if auth_header:
            try:
                # Parse the Authorization header
                auth_type, auth_credentials = auth_header.split(" ", 1)
                if auth_type.lower() == "basic":
                    # Decode the Base64-encoded credentials
                    decoded_credentials = base64.b64decode(auth_credentials).decode("utf-8")
                    username, password = decoded_credentials.split(":", 1)
                    
                    # Check if credentials match
                    if secrets.compare_digest(username, APP_USERNAME) and secrets.compare_digest(password, APP_PASSWORD):
                        # Credentials match, allow the request to proceed
                        return await call_next(request)
            except Exception:
                # Any exception during auth processing results in auth failure
                pass
        
        # If we reach here, authentication failed or was not provided
        # Return 401 Unauthorized with WWW-Authenticate header to prompt for credentials
        headers = {"WWW-Authenticate": "Basic"}
        
        # Check if this is a WebSocket upgrade request
        if "upgrade" in request.headers.get("connection", "").lower() and request.headers.get("upgrade", "").lower() == "websocket":
            # For WebSocket connections, return a 401 immediately
            return Response(status_code=HTTP_401_UNAUTHORIZED, headers=headers)
        
        # For regular HTTP requests, return a 401 with a message
        return Response(
            content="Unauthorized. Authentication required.",
            status_code=HTTP_401_UNAUTHORIZED,
            headers=headers
        )

llm_client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_KEY
)

app = FastAPI()

# Add Basic Auth middleware
app.add_middleware(BasicAuthMiddleware)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

log_file = open("log.txt", "w")
model_size = "distil-large-v3"
asr = FasterWhisperASR("en", model_size, logfile=log_file) 
online = VACOnlineASRProcessor(online_chunk_size=0.5, asr=asr) 

sample_rate = 16000
chunk_ms = 500
capture_duration_secs = 0.5


llm_client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_KEY
)

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
        <p id='transcript'></p>
        <button id="saveButton">Save Transcript</button>
        <button id="generateReportButton">Generate Report</button>
        <br>
        <textarea id="reportTextArea" rows="10" cols="50" readonly></textarea>
        <script>
            let ws;
            let audioContext;
            let source;
            let processor;
            let stream;
            const startButton = document.getElementById('startButton');
            const stopButton = document.getElementById('stopButton');
            const saveButton = document.getElementById('saveButton');
            const generateReportButton = document.getElementById('generateReportButton');

            startButton.onclick = startStreaming;
            stopButton.onclick = stopStreaming;
            saveButton.onclick = saveTranscript;
            generateReportButton.onclick = generateReport;

            function startStreaming() {
                ws = new WebSocket("ws://localhost:8000/ws");
                ws.onmessage = function(event) {
                    var transcript = document.getElementById('transcript');
                    var content = document.createTextNode(event.data);
                    transcript.appendChild(content);
                };

                navigator.mediaDevices.getUserMedia({ audio: true })
                    .then(streamObj => {
                        stream = streamObj;
                        // Create audio context with lower sample rate
                        audioContext = new AudioContext();
                        source = audioContext.createMediaStreamSource(stream);
                        
                        // Create processor with desired chunk size (4096 samples)
                        processor = audioContext.createScriptProcessor(4096, 1, 1);
                        
                        // Create a resampler to convert to 16000Hz
                        const resampleRatio = 16000 / audioContext.sampleRate;
                        
                        source.connect(processor);
                        processor.connect(audioContext.destination);
                        
                        processor.onaudioprocess = function(e) {
                            // Get original audio data
                            const inputData = e.inputBuffer.getChannelData(0);
                            
                            // Perform simple resampling
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

            function saveTranscript() {
                const transcript = document.getElementById('transcript').textContent;
                const blob = new Blob([transcript], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'transcript.txt';
                a.click();
                URL.revokeObjectURL(url);
            }

            function generateReport() {
                const transcript = document.getElementById('transcript').textContent;
                report = fetch("http://localhost:8000/generate_report", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        transcript: transcript
                    })
                })
                .then(response => response.json())
                .then(data => {
                    const reportTextArea = document.getElementById('reportTextArea');
                    reportTextArea.value = data.report;
                    reportTextArea.rows = 10;
                    reportTextArea.cols = 50;
                    reportTextArea.readOnly = true;
                })
            }

            function stopStreaming() {
                // Disconnect the audio processing pipeline
                if (processor && source) {
                    processor.disconnect();
                    source.disconnect();
                }
                
                // Close the AudioContext
                if (audioContext) {
                    // Modern browsers require closing the AudioContext
                    if (audioContext.state !== 'closed' && typeof audioContext.close === 'function') {
                        audioContext.close();
                    }
                }
                
                // Stop all audio tracks
                if (stream) {
                    stream.getTracks().forEach(track => track.stop());
                }
                
                // Close the WebSocket connection
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.close();
                }
                
                // Reset UI
                startButton.disabled = false;
                stopButton.disabled = true;
                
                // Optional: clear the transcript or add a separator
                let separator_dashed_line = document.createElement('hr');
                separator_dashed_line.style.borderTop = '1px dashed #000';
                document.getElementById('transcript').appendChild(separator_dashed_line);
            }
        </script>
    </body>
</html>
"""


@app.get("/old_home")
async def get():
    return HTMLResponse(html)

@app.get("/", response_class=HTMLResponse)
async def get_html():
    try:
        with open("index.html", "r") as file:
            return file.read()
    except FileNotFoundError:
        # If file doesn't exist, serve the embedded HTML
        with open("index.html", "w") as file:
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>...</head>
            <body>...</body>
            </html>
            """  # This would be the full HTML from the artifact
            file.write(html_content)
            return html_content


@app.post("/generate_outline")
async def generate_outline(request: Request):
    transcript_data = await request.json()
    print(json.dumps(transcript_data, indent=4))
    article_style = transcript_data.get("articleStyle", "default")

    outline = outline_report(llm_client, transcript_data["transcript"], article_style)
    return outline

@app.post("/generate_report")
async def generate_report(request: Request):
    transcript_data = await request.json()
    print(json.dumps(transcript_data, indent=4))
    article_style = transcript_data.get("articleStyle", "default")
    report = generate_report_from_outline(llm_client, transcript_data["transcript"], transcript_data["outline"], article_style)
    return report

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    sample_rate = 16000
    
    # Buffer to accumulate audio samples
    audio_buffer = np.array([], dtype=np.float32)
    
    samples_per_chunk = capture_duration_secs * sample_rate
    
    while True:
        try:
            data = await websocket.receive_bytes()
            if not data:
                continue
                
            chunk = np.frombuffer(data, dtype=np.float32)
            online.insert_audio_chunk(chunk)
            # Add to buffer
            audio_buffer = np.append(audio_buffer, chunk)
            
            # Process if we have enough data
            if len(audio_buffer) >= samples_per_chunk:
                # Transcribe
                time_start = time.time()
                st, end, text = online.process_iter()
                time_end = time.time()
                if text != "":
                    await websocket.send_text(text)
                print(f"the latency is {time_end-time_start:.2f}")

                audio_buffer = np.array([], dtype=np.float32)
                
        except Exception as e:
            print(f"WebSocket error: {e}")
            break
