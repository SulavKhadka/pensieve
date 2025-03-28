// DOM Elements
const startButton = document.getElementById('startButton');
const stopButton = document.getElementById('stopButton');
const clearButton = document.getElementById('clearButton');
const saveButton = document.getElementById('saveButton');
const generateOutlineButton = document.getElementById('generateOutlineButton');
const generateReportButton = document.getElementById('generateReportButton');
const copyReportButton = document.getElementById('copyReportButton');
const downloadReportButton = document.getElementById('downloadReportButton');
const settingsBtn = document.getElementById('settingsBtn');
const closeModalBtn = document.getElementById('closeModalBtn');
const saveSettingsBtn = document.getElementById('saveSettingsBtn');

const settingsModal = document.getElementById('settingsModal');
const toast = document.getElementById('toast');
const toastMessage = document.getElementById('toastMessage');
const transcript = document.getElementById('transcript');
const articleStyle = document.getElementById('articleStyle');
const customStyle = document.getElementById('customStyle');
const reportContent = document.getElementById('reportContent');
const outlineContent = document.getElementById('outlineContent');
const recordingIndicator = document.getElementById('recordingIndicator');
const visualizerBars = document.getElementById('visualizerBars');
const reportTypeOptions = document.querySelectorAll('.report-type-option');
const tabs = document.querySelectorAll('.tab');
const tabContents = document.querySelectorAll('.tab-content');

// Configure marked.js options
marked.setOptions({
    gfm: true,
    breaks: true,
    pedantic: false,
    sanitize: false,
    smartLists: true,
    smartypants: false,
    xhtml: false,
    highlight: function(code, lang) {
        return code;
    }
});

// App State
let ws;
let audioContext;
let source;
let processor;
let stream;
let analyser;
let isRecording = false;
let visualizerInterval;
let hasOutline = false; // Track if outline has been generated
let settings = {
    language: 'en',
    transcriptionModel: 'distil-large-v3',
    reportModel: 'google/gemini-2.0-flash-001',
    reportType: 'summary'
};

// Style descriptions for different report styles
const styleDescriptions = {
    'academic': 'Formal, structured writing with citations, technical terminology, and evidence-based arguments. Suitable for research papers and scholarly articles.',
    'business': 'Clear, concise, and action-oriented with executive summaries, data-driven insights, and professional tone. Ideal for business reports and proposals.',
    'creative': 'Expressive, imaginative writing with vivid descriptions, narrative elements, and engaging storytelling techniques.',
    'journalistic': 'Objective, fact-based reporting with clear headlines, concise paragraphs, and the inverted pyramid structure (most important information first).',
    'technical': 'Precise, detailed explanations with specialized terminology, step-by-step instructions, and diagrams or code examples where appropriate.',
    'narrative': 'Story-driven approach with character development, plot progression, and descriptive scenes that engage the reader emotionally.',
    'blog': 'Conversational, accessible tone with personal insights, practical advice, and engaging headings. Often includes lists and actionable takeaways.'
};

// Load settings from localStorage if available
function loadSettings() {
    const savedSettings = localStorage.getItem('voiceScribeSettings');
    if (savedSettings) {
        settings = JSON.parse(savedSettings);
        
        // Update UI to reflect saved settings
        document.getElementById('languageSelect').value = settings.language;
        document.getElementById('modelSelect').value = settings.transcriptionModel;
        document.getElementById('reportModelSelect').value = settings.reportModel;
        
        // Update report type selection
        reportTypeOptions.forEach(option => {
            if (option.dataset.type === settings.reportType) {
                option.classList.add('active');
            } else {
                option.classList.remove('active');
            }
        });
    }
}

// Save settings to localStorage
function saveSettings() {
    localStorage.setItem('voiceScribeSettings', JSON.stringify(settings));
    showToast('Settings saved successfully!', 'success');
    settingsModal.style.display = 'none';
}

// Initialize audio visualizer
function initVisualizer() {
    const visualizerBars = document.getElementById('visualizerBars');
    visualizerBars.innerHTML = ''; // Clear existing bars
    const barCount = 30;
    
    // Create initial bars
    for (let i = 0; i < barCount; i++) {
        const bar = document.createElement('div');
        bar.className = 'visualizer-bar';
        bar.style.height = '3px';
        visualizerBars.appendChild(bar);
    }
}

// Update visualizer with audio data
function updateVisualizer() {
    if (!isRecording) {
        // Clear all bars when not recording
        const visualizerBars = document.getElementById('visualizerBars');
        const bars = visualizerBars.querySelectorAll('.visualizer-bar');
        bars.forEach(bar => {
            bar.style.height = '3px';
        });
        return;
    }
    
    const visualizerBars = document.getElementById('visualizerBars');
    const bars = visualizerBars.querySelectorAll('.visualizer-bar');
    
    // Use actual audio data from the analyser
    if (analyser) {
        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(dataArray);
        
        const barCount = bars.length;
        const step = Math.floor(dataArray.length / barCount);
        
        for (let i = 0; i < barCount; i++) {
            // Scale the value to a reasonable height
            const value = dataArray[i * step] / 4;
            bars[i].style.height = `${value}px`;
        }
    }
    
    // Schedule next update
    visualizerInterval = setTimeout(updateVisualizer, 50);
}

// Start audio streaming
function startStreaming() {
    if (isRecording) return;
    
    // Create WebSocket connection with protocol matching page protocol (ws or wss)
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);
    
    ws.onopen = function() {
        // Request audio permissions
        navigator.mediaDevices.getUserMedia({ audio: true })
            .then(streamObj => {
                stream = streamObj;
                
                // Create audio context
                audioContext = new AudioContext();
                source = audioContext.createMediaStreamSource(stream);
                
                // Create analyzer for visualizer
                analyser = audioContext.createAnalyser();
                analyser.fftSize = 256;
                source.connect(analyser);
                
                // Create processor with desired chunk size
                processor = audioContext.createScriptProcessor(4096, 1, 1);
                source.connect(processor);
                processor.connect(audioContext.destination);
                
                // Process audio data
                processor.onaudioprocess = function(e) {
                    if (ws.readyState === WebSocket.OPEN) {
                        // Get original audio data
                        const inputData = e.inputBuffer.getChannelData(0);
                        
                        // Resample to 16000Hz
                        const resampleRatio = 16000 / audioContext.sampleRate;
                        const resampledLength = Math.floor(inputData.length * resampleRatio);
                        const resampledData = new Float32Array(resampledLength);
                        
                        for (let i = 0; i < resampledLength; i++) {
                            const idx = i / resampleRatio;
                            const idx1 = Math.floor(idx);
                            const idx2 = Math.min(idx1 + 1, inputData.length - 1);
                            const frac = idx - idx1;
                            resampledData[i] = inputData[idx1] * (1 - frac) + inputData[idx2] * frac;
                        }
                        
                        // Send resampled audio data to server
                        ws.send(resampledData.buffer);
                    }
                };
                
                // Update UI
                startButton.disabled = true;
                stopButton.disabled = false;
                recordingIndicator.style.display = 'flex';
                isRecording = true;
                
                // Start visualizer update
                visualizerInterval = setTimeout(updateVisualizer, 100);
                
                showToast('Recording started', 'success');
            })
            .catch(error => {
                console.error('Error accessing microphone:', error);
                showToast('Could not access microphone', 'error');
                ws.close();
            });
    };
    
    ws.onmessage = function(event) {
        const content = document.createTextNode(event.data);
        
        transcript.appendChild(content);
        
        // Auto-scroll to the bottom
        transcript.scrollTop = transcript.scrollHeight;
    };
    
    ws.onerror = function(error) {
        console.error('WebSocket error:', error);
        showToast('Connection error', 'error');
        stopStreaming();
    };
    
    ws.onclose = function() {
        if (isRecording) {
            stopStreaming();
        }
    };
}

// Stop audio streaming
function stopStreaming() {
    isRecording = false;
    
    // Clear visualizer interval
    if (visualizerInterval) {
        clearTimeout(visualizerInterval);
        visualizerInterval = null;
    }
    
    // Ensure visualizer is cleared
    updateVisualizer(); // This will clear the bars since isRecording is false
    
    // Disconnect the audio processing pipeline
    if (processor && source) {
        processor.disconnect();
        source.disconnect();
    }
    
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
    }
    
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close();
    }
    
    // Reset variables
    audioContext = null;
    source = null;
    processor = null;
    stream = null;
    analyser = null;
    
    // Update UI
    startButton.disabled = false;
    stopButton.disabled = true;
    recordingIndicator.style.display = 'none';
    
    showToast('Recording stopped', 'success');
}

// Clear transcript
function clearTranscript() {
    if (confirm('Are you sure you want to clear the transcript?')) {
        transcript.innerHTML = '';
        showToast('Transcript cleared', 'success');
    }
}

// Save transcript
function saveTranscript() {
    const text = transcript.innerText;
    if (!text.trim()) {
        showToast('No transcript to save', 'error');
        return;
    }
    
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transcript_${new Date().toISOString().split('T')[0]}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    
    showToast('Transcript saved', 'success');
}

// Tab handling
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        // Remove active class from all tabs and contents
        tabs.forEach(t => t.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));
        
        // Add active class to clicked tab and corresponding content
        tab.classList.add('active');
        const content = document.querySelector(`.tab-content[data-content="${tab.dataset.tab}"]`);
        content.classList.add('active');
    });
});

// Generate report
async function generateReport() {
    document.querySelector('.tab[data-tab="outline"]').classList.remove('active');
    document.querySelector(`.tab-content[data-content="outline"]`).classList.remove('active');
    
    document.querySelector('.tab[data-tab="report"]').classList.add('active');
    document.querySelector(`.tab-content[data-content="report"]`).classList.add('active');
    
    const text = transcript.innerText;
    if (!text.trim()) {
        showToast('No transcript to generate report from', 'error');
        return;
    }
    
    // Set loading state
    generateReportButton.disabled = true;
    generateReportButton.innerHTML = '<div class="spinner"></div>';
    reportContent.innerHTML = 'Generating final report...';
    
    try {
        // Get the edited outline content - look for the editable div first
        const editableOutline = outlineContent.querySelector('.editable-outline');
        const outline = editableOutline ? editableOutline.innerHTML : outlineContent.innerHTML;
        
        reportContent.innerHTML = 'Generating final report...';
        
        // Then generate the report using the outline
        const reportResponse = await fetch(`${window.location.protocol}//${window.location.host}/generate_report`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                transcript: text,
                outline: outline,
                articleStyle: customStyle.value,
            })
        });
        
        if (!reportResponse.ok) {
            throw new Error('Failed to generate report');
        }
        
        const report = await reportResponse.json();
        console.log(report.report);
        reportContent.innerHTML = marked.parse(report.report);
        showToast('Report generated successfully', 'success');
        
        // Enable copy and download buttons
        copyReportButton.disabled = false;
        downloadReportButton.disabled = false;
        
    } catch (error) {
        console.error('Error generating report:', error);
        reportContent.innerHTML = 'Error generating report. Please try again.';
        showToast('Failed to generate report', 'error');

        // Disable copy and download buttons
        copyReportButton.disabled = true;
        downloadReportButton.disabled = true;
        
    } finally {
        // Reset button state
        generateReportButton.disabled = false;
        generateReportButton.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="16"></line>
                <line x1="8" y1="12" x2="16" y2="12"></line>
            </svg>
            Generate Report
        `;
    }
}

// Generate Outline
async function generateOutline() {
    const text = transcript.innerText;
    if (!text.trim()) {
        showToast('No transcript to generate outline from', 'error');
        return;
    }
    
    // Get the selected style or custom style
    let selectedStyle = articleStyle.value;
    if (customStyle.value.trim()) {
        selectedStyle = customStyle.value.trim();
    }
    
    // Set loading state
    generateOutlineButton.disabled = true;
    generateOutlineButton.innerHTML = '<div class="spinner"></div>';
    outlineContent.innerHTML = 'Generating outline...';
    
    console.log(articleStyle.value);
    console.log(customStyle.value);

    try {
        // Make API call to generate outline
        const response = await fetch(`${window.location.protocol}//${window.location.host}/generate_outline`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                transcript: text,
                articleStyle: customStyle.value
            })
        });
        
        if (!response.ok) {
            throw new Error('Failed to generate outline');
        }
        
        const outline = await response.json();
        
        // Create an editable div with the outline content
        outlineContent.innerHTML = `
            <div class="editable-outline" contenteditable="true">${marked.parse(outline.outline)}</div>
            <div class="outline-edit-hint">You can edit this outline before generating the report</div>
        `;
        
        hasOutline = true;
        
        // Switch to outline tab
        document.querySelector('.tab[data-tab="outline"]').classList.add('active');
        document.querySelector('.tab[data-tab="report"]').classList.remove('active');
        document.querySelector(`.tab-content[data-content="outline"]`).classList.add('active');
        document.querySelector(`.tab-content[data-content="report"]`).classList.remove('active');
        
        showToast('Outline generated successfully. You can now edit it.', 'success');
        
    } catch (error) {
        console.error('Error generating outline:', error);
        outlineContent.innerHTML = 'Error generating outline. Please try again.';
        showToast('Failed to generate outline', 'error');
        
    } finally {
        // Reset button state
        generateOutlineButton.disabled = false;
        generateOutlineButton.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="16"></line>
                <line x1="8" y1="12" x2="16" y2="12"></line>
            </svg>
            Generate Outline
        `;
    }
}

// Copy report to clipboard
function copyReport() {
    const text = reportContent.innerText;
    if (!text) {
        showToast('No report to copy', 'error');
        return;
    }
    
    navigator.clipboard.writeText(text).then(() => {
        showToast('Report copied to clipboard', 'success');
    }, () => {
        showToast('Failed to copy report', 'error');
    });
}

// Download report
function downloadReport() {
    const text = reportContent.innerText;
    if (!text) {
        showToast('No report to download', 'error');
        return;
    }
    
    // Get raw markdown content
    const markdownContent = reportContent.getAttribute('data-markdown') || text;
    
    const blob = new Blob([markdownContent], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `report-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
    
    showToast('Report downloaded', 'success');
}

// Show toast notification
function showToast(message, type = 'success') {
    toastMessage.textContent = message;
    toast.className = `toast ${type} visible`;
    
    // Hide toast after 3 seconds
    setTimeout(() => {
        toast.classList.remove('visible');
    }, 3000);
}

// Initialize visualizer
initVisualizer();

// Load saved settings
loadSettings();

// Event listeners
startButton.addEventListener('click', startStreaming);
stopButton.addEventListener('click', stopStreaming);
clearButton.addEventListener('click', clearTranscript);
saveButton.addEventListener('click', saveTranscript);
generateOutlineButton.addEventListener('click', generateOutline);
generateReportButton.addEventListener('click', generateReport);
copyReportButton.addEventListener('click', copyReport);
downloadReportButton.addEventListener('click', downloadReport);

// Settings modal
settingsBtn.addEventListener('click', () => {
    settingsModal.style.display = 'flex';
});

closeModalBtn.addEventListener('click', () => {
    settingsModal.style.display = 'none';
});

saveSettingsBtn.addEventListener('click', saveSettings);

// Report type selection
reportTypeOptions.forEach(option => {
    option.addEventListener('click', () => {
        // Remove active class from all options
        reportTypeOptions.forEach(opt => opt.classList.remove('active'));
        
        // Add active class to clicked option
        option.classList.add('active');
        
        // Update settings
        settings.reportType = option.dataset.type;
    });
});

// Style selector event listener
articleStyle.addEventListener('change', () => {
    const selectedStyle = articleStyle.value;
    customStyle.value = styleDescriptions[selectedStyle] || 'Select a style to see its description.';
});

// Initialize style description
customStyle.value = styleDescriptions[articleStyle.value] || 'Select a style to see its description.';

// Tab switching
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        // Remove active class from all tabs and contents
        tabs.forEach(t => t.classList.remove('active'));
        tabContents.forEach(content => content.classList.remove('active'));
        
        // Add active class to clicked tab and corresponding content
        tab.classList.add('active');
        const tabName = tab.dataset.tab;
        document.querySelector(`.tab-content[data-content="${tabName}"]`).classList.add('active');
    });
});

// Close modal when clicking outside
window.addEventListener('click', (event) => {
    if (event.target === settingsModal) {
        settingsModal.style.display = 'none';
    }
});

// Disable copy and download buttons initially
copyReportButton.disabled = true;
downloadReportButton.disabled = true;

// Handle page unload
window.addEventListener('beforeunload', () => {
    if (isRecording) {
        stopStreaming();
    }
});