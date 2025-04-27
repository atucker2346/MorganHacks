// Get References to Practice Page Elements
const feedbackContentDiv = document.getElementById('feedback-content');
const wpmValueSpan = document.getElementById('wpm-value');
const pacingValueSpan = document.getElementById('pacing-value');
const fillerCountSpan = document.getElementById('filler-count');
const transcriptDisplay = document.getElementById('transcript-display');
const tipsList = document.getElementById('tips-list');
const notesListDiv = document.getElementById('notes-list');
const saveButton = document.getElementById('saveSpeechButton');
const startButton = document.querySelector(".cta-button");

// Helper functions
function setLoadingState(isLoading) {
    const loadingTexts = document.querySelectorAll('.loading-text');
    const loadingBlocks = document.querySelectorAll('.loading-block');

    if (isLoading) {
        loadingTexts.forEach(el => { if(el) el.style.display = 'inline'; });
        loadingBlocks.forEach(el => { if(el) el.style.display = 'block'; });
        if (wpmValueSpan) wpmValueSpan.textContent = '(...)';
        if (pacingValueSpan) pacingValueSpan.textContent = '(...)';
        if (fillerCountSpan) fillerCountSpan.textContent = '(...)';
        if (transcriptDisplay) transcriptDisplay.value = 'Loading transcript...';
        if (feedbackContentDiv) feedbackContentDiv.innerHTML = '<p class="loading-block">Loading feedback...</p>';
        if (tipsList) tipsList.innerHTML = '<li class="loading-block">Loading tips...</li>';
        if (notesListDiv) notesListDiv.innerHTML = '<p class="loading-block">Loading notes...</p>';
        if (saveButton) saveButton.disabled = true;
    } else {
        loadingTexts.forEach(el => { if(el) el.style.display = 'none'; });
        loadingBlocks.forEach(el => { if(el) el.style.display = 'none'; });
    }
}

function calculatePacing(wpm) {
    if (wpm < 120) return 'Too Slow';
    if (wpm < 150) return 'Good';
    if (wpm < 180) return 'Excellent';
    return 'Too Fast';
}

function generateNotecardsFromTranscript(transcript) {
    if (!transcript) return [];
    
    const sentences = transcript.split(/[.!?]+/).filter(s => s.trim().length > 0);
    const notecards = [];
    
    for (let i = 0; i < Math.min(sentences.length, 3); i++) {
        if (sentences[i].trim().length > 20) {
            notecards.push(sentences[i].trim());
        }
    }
    
    return notecards;
}

function generateFeedbackText(session) {
    let feedback = '';
    
    if (session.wpm < 120) {
        feedback += 'Your speaking pace is a bit slow. Try to increase your speed slightly. ';
    } else if (session.wpm > 180) {
        feedback += 'You are speaking quite fast. Try to slow down for better clarity. ';
    } else {
        feedback += 'Your pace is good! ';
    }
    
    if (session.filler_count > 10) {
        feedback += 'You used a lot of filler words. Work on reducing "um", "uh", and similar words.';
    } else if (session.filler_count > 5) {
        feedback += 'You used some filler words. Try to be more conscious of them.';
    } else {
        feedback += 'Great job on minimizing filler words!';
    }
    
    return feedback;
}

// Utility function
function showTemporaryMessage(message) {
    const existingMessage = document.getElementById('temp-message-box');
    if (existingMessage) existingMessage.remove();
    const messageDiv = document.createElement('div');
    messageDiv.id = 'temp-message-box';
    messageDiv.textContent = message;
    messageDiv.style.position = 'fixed'; 
    messageDiv.style.bottom = '20px'; 
    messageDiv.style.left = '50%'; 
    messageDiv.style.transform = 'translateX(-50%)';
    messageDiv.style.backgroundColor = 'var(--primary-purple)'; 
    messageDiv.style.color = 'var(--text-color)'; 
    messageDiv.style.padding = '12px 25px';
    messageDiv.style.borderRadius = '8px'; 
    messageDiv.style.zIndex = '1001'; 
    messageDiv.style.opacity = '1';
    messageDiv.style.transition = 'opacity 0.5s ease-out 2.5s'; 
    messageDiv.style.boxShadow = '0 3px 10px rgba(0,0,0,0.3)';
    document.body.appendChild(messageDiv);
    setTimeout(() => {
        messageDiv.style.opacity = '0';
        setTimeout(() => { if (messageDiv.parentNode) messageDiv.remove(); }, 500);
    }, 3000);
}

window.fetchAndUpdatePracticeData = async function() {
    console.log("🏃‍♂️ fetchAndUpdatePracticeData() has started");
    console.log("Fetching latest speech data...");
    setLoadingState(true); // Show loading indicators

    try {
        const response = await fetch('/api/latest_practice_data');
        if (!response.ok) {
            let errorMsg = `HTTP error! status: ${response.status}`;
            if (response.status === 404) errorMsg = "Error: Backend endpoint /api/latest_practice_data not found (404). Check your server.";
            else if (response.status === 500) errorMsg = "Error: Server error (500). Check server logs.";
            throw new Error(errorMsg);
        }
        
        const data = await response.json();
        console.log("Successfully fetched data:", data);

        // Process data ONLY ONCE using mappedData
        const mappedData = {
            wpm: data.practice_session.wpm,
            pacing: calculatePacing(data.practice_session.wpm),
            filler_count: data.practice_session.filler_count,
            transcript: data.practice_session.transcript,
            feedback_speech: generateFeedbackText(data.practice_session),
            feedback_posture: data.practice_session.final_posture || 'No posture data',
            notecards: generateNotecardsFromTranscript(data.practice_session.transcript)
        };

        console.log("Mapped Data:", mappedData)

        // Update all UI elements with mappedData
        if (wpmValueSpan) {
            wpmValueSpan.textContent = mappedData.wpm ?? 'N/A';
            wpmValueSpan.classList.remove('loading-text');
            wpmValueSpan.style.display = 'inline';
        }
        if (pacingValueSpan) {
            pacingValueSpan.textContent = mappedData.pacing ?? 'N/A';
            pacingValueSpan.classList.remove('loading-text');
            pacingValueSpan.style.display = 'inline';
        }
        if (fillerCountSpan) {
            fillerCountSpan.textContent = mappedData.filler_count ?? 'N/A';
            fillerCountSpan.classList.remove('loading-text');
            fillerCountSpan.style.display = 'inline';
        }
        if (transcriptDisplay) transcriptDisplay.value = mappedData.transcript ?? 'No transcript available.';

        if (feedbackContentDiv) {
            feedbackContentDiv.innerHTML = ''; // Clear previous
            const speechP = document.createElement('p');
            speechP.innerHTML = `<strong>Speech:</strong> ${mappedData.feedback_speech || 'No speech feedback provided.'}`;
            const postureP = document.createElement('p');
            postureP.innerHTML = `<strong>Posture:</strong> ${mappedData.feedback_posture || 'No posture feedback provided.'}`;
            feedbackContentDiv.appendChild(speechP);
            feedbackContentDiv.appendChild(postureP);
        }

        if (tipsList) {
            tipsList.innerHTML = ''; // Clear previous
            const combinedFeedback = `${mappedData.feedback_speech || ''} ${mappedData.feedback_posture || ''}`;
            const potentialTips = combinedFeedback.split(/[.]+/g).map(tip => tip.trim()).filter(tip => tip.length > 10);
            if (potentialTips.length > 0) {
                potentialTips.forEach(tipText => {
                    const li = document.createElement('li');
                    li.textContent = tipText + '.';
                    tipsList.appendChild(li);
                });
            } else if (mappedData.transcript && mappedData.transcript !== 'N/A') {
                tipsList.innerHTML = '<li>Looks good! Keep practicing to refine further.</li>';
            } else {
                tipsList.innerHTML = '<li class="loading-block">No tips available yet.</li>';
            }
        }

        if (notesListDiv) {
            notesListDiv.innerHTML = ''; // Clear previous
            if (mappedData.notecards && Array.isArray(mappedData.notecards) && mappedData.notecards.length > 0) {
                mappedData.notecards.forEach(noteText => {
                    if (noteText) {
                        const noteCard = document.createElement('div'); 
                        noteCard.className = 'note-card';
                        const noteIcon = document.createElement('div'); 
                        noteIcon.className = 'note-icon'; 
                        noteIcon.textContent = '📝';
                        const noteTextDiv = document.createElement('div'); 
                        noteTextDiv.className = 'note-text'; 
                        noteTextDiv.textContent = noteText;
                        noteCard.appendChild(noteIcon); 
                        noteCard.appendChild(noteTextDiv);
                        notesListDiv.appendChild(noteCard);
                    }
                });
            } else if (mappedData.transcript && mappedData.transcript !== 'N/A') {
                notesListDiv.innerHTML = '<p>No specific note cards generated for this session.</p>';
            } else {
                notesListDiv.innerHTML = '<p class="loading-block">No note cards available yet.</p>';
            }
        }
    } catch (e) {
        console.error('Error fetching or updating speech data:', e);
        if (feedbackContentDiv) feedbackContentDiv.innerHTML = `<p style="color: #ff6b6b;">⚠️ Error loading feedback: ${e.message}</p>`;
        if (tipsList) tipsList.innerHTML = `<li style="color: #ff6b6b;">⚠️ Error loading tips</li>`;
        if (notesListDiv) notesListDiv.innerHTML = `<p style="color: #ff6b6b;">⚠️ Error loading notes</p>`;
        if (wpmValueSpan) wpmValueSpan.textContent = 'Err';
        if (pacingValueSpan) pacingValueSpan.textContent = 'Err';
        if (fillerCountSpan) fillerCountSpan.textContent = 'Err';
        if (transcriptDisplay) transcriptDisplay.value = `Error loading data: ${e.message}`;
        showDemoPracticeData();
    } finally {
        setLoadingState(false); // Hide loading indicators
    }
};

document.addEventListener('DOMContentLoaded', function() {
    if (startButton) {
        startButton.addEventListener("click", async e => {
            e.preventDefault();
            await fetch("/start-practice", { method: "POST", headers: { "Content-Type": "application/json" } });
            showPage("practice-page", true);
        });
        }

    // Determine which page we're on
    const currentPath = window.location.pathname;
    console.log("Current path:", currentPath);

    // Find out which page we're on and initialize it
    if (/\/practice(\.html)?$/.test(location.pathname)) {
        window.fetchAndUpdatePracticeData();
    } else if (currentPath.includes('history.html') || currentPath.endsWith('history')) {
        console.log("History page detected");
        if (typeof loadSpeechHistory === 'function') {
            loadSpeechHistory();
        } else {
            console.error("loadSpeechHistory function not found!");
        }
    } else if (currentPath.includes('notes.html') || currentPath.endsWith('notes')) {
        console.log("Notes page detected");
        if (typeof loadSavedNotecards === 'function') {
            loadSavedNotecards();
        } else {
            console.error("loadSavedNotecards function not found!");
        }
    } else {
        console.log("Home page or unknown page detected");
        // Home page initialization if needed
    }

    if (startButton) {
    startButton.addEventListener("click", async e => {
        e.preventDefault();
        await fetch("/start-practice", { method: "POST" });
        showPage("practice-page", true);
    });
    }


    // Save button functionality
    if (saveButton) {
        saveButton.addEventListener('click', function() {
            console.log('Save Speech button clicked! (Functionality not implemented)');
            showTemporaryMessage('Save Speech functionality is planned for a future update.');
        });
    }

    console.log('Speech Analysis page setup complete.');
});