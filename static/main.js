// Speech Analysis Tool - Main JavaScript File
document.addEventListener('DOMContentLoaded', function() {
    // Check which page we're on and load the appropriate content
    const currentPath = window.location.pathname;
    
    if (currentPath.includes('practice.html')) {
        // Script.js handles practice page initialization
        console.log('Practice page detected - handled by script.js');
    } else if (currentPath.includes('history.html')) {
        loadSpeechHistory();
    } else if (currentPath.includes('notes.html')) {
        loadSavedNotecards();
    } else if (currentPath.includes('home.html') || currentPath === '/' || currentPath === '') {
        initHomePage();
    }
});

// This function is needed by script.js
function showDemoPracticeData() {
    // Demo data for development and testing
    const demoData = {
        session_id: 0,
        timestamp: new Date().toISOString(),
        duration_seconds: 137,
        total_words: 382,
        wpm: 167,
        filler_count: 7,
        final_posture: 'Good',
        transcript: 'Today I want to discuss the importance of public speaking. Being able to communicate effectively is crucial in both personal and professional settings. When we can articulate our thoughts clearly, we have a much better chance of connecting with our audience and having our message understood. Public speaking is a skill that can be developed with practice and feedback.'
    };
    
    // Get references to practice page elements
    const feedbackContentDiv = document.getElementById('feedback-content');
    const wpmValueSpan = document.getElementById('wpm-value');
    const pacingValueSpan = document.getElementById('pacing-value');
    const fillerCountSpan = document.getElementById('filler-count');
    const transcriptDisplay = document.getElementById('transcript-display');
    const tipsList = document.getElementById('tips-list');
    const notesListDiv = document.getElementById('notes-list');
    const saveButton = document.getElementById('saveSpeechButton');
    
    // Update UI with demo data
    if (wpmValueSpan) wpmValueSpan.textContent = demoData.wpm;
    if (pacingValueSpan) pacingValueSpan.textContent = 'Good'; // Hard-coded value
    if (fillerCountSpan) fillerCountSpan.textContent = demoData.filler_count;
    if (transcriptDisplay) transcriptDisplay.value = demoData.transcript;
    
    if (feedbackContentDiv) {
        feedbackContentDiv.innerHTML = '';
        const speechP = document.createElement('p');
        speechP.innerHTML = '<strong>Speech:</strong> Your pace is good! Great job on minimizing filler words!';
        const postureP = document.createElement('p');
        postureP.innerHTML = `<strong>Posture:</strong> ${demoData.final_posture}`;
        feedbackContentDiv.appendChild(speechP);
        feedbackContentDiv.appendChild(postureP);
    }
    
    if (tipsList) {
        tipsList.innerHTML = '';
        const tips = [
            'Practice speaking with a metronome to maintain consistent pacing.',
            'Record yourself and review the recordings to identify areas for improvement.',
            'Use natural hand gestures to emphasize key points.'
        ];
        tips.forEach(tip => {
            const li = document.createElement('li');
            li.textContent = tip;
            tipsList.appendChild(li);
        });
    }
    
    if (notesListDiv) {
        notesListDiv.innerHTML = '';
        const sentences = demoData.transcript.split(/[.!?]+/).filter(s => s.trim().length > 0);
        for (let i = 0; i < Math.min(sentences.length, 3); i++) {
            if (sentences[i].length > 30) {
                const noteCard = document.createElement('div');
                noteCard.className = 'note-card';
                const noteIcon = document.createElement('div');
                noteIcon.className = 'note-icon';
                noteIcon.textContent = '📝';
                const noteTextDiv = document.createElement('div');
                noteTextDiv.className = 'note-text';
                noteTextDiv.textContent = sentences[i].trim();
                noteCard.appendChild(noteIcon);
                noteCard.appendChild(noteTextDiv);
                notesListDiv.appendChild(noteCard);
            }
        }
    }
    
    // Enable save button if it exists
    if (saveButton) saveButton.disabled = false;
}

// History Page Functions
function loadSpeechHistory() {
    console.log('Loading speech history...');
    
    // In a real application, this would fetch from your Python backend
    fetch('/api/speech_history')
        .then(response => response.json())
        .then(data => {
            if (data && data.success) {
                displaySpeechHistory(data.sessions);
                setupHistoryListeners();
            } else {
                // Show demo data if no history is available
                displaySpeechHistory(getDemoHistorySessions());
                setupHistoryListeners();
            }
        })
        .catch(error => {
            console.error('Error fetching speech history:', error);
            displaySpeechHistory(getDemoHistorySessions());
            setupHistoryListeners();
        });
}

function displaySpeechHistory(sessions) {
    const container = document.getElementById('history-container');
    container.innerHTML = '';
    
    if (!sessions || sessions.length === 0) {
        const emptyMessage = document.createElement('p');
        emptyMessage.textContent = 'No speech practice sessions found. Start practicing to build your history!';
        container.appendChild(emptyMessage);
        return;
    }
    
    sessions.forEach(session => {
        const sessionItem = document.createElement('div');
        sessionItem.className = 'history-item';
        sessionItem.dataset.sessionId = session.session_id;
        
        const date = new Date(session.timestamp);
        const formattedDate = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
        
        sessionItem.innerHTML = `
            <div class="history-item-header">
                <h3>${formattedDate}</h3>
                <span class="badge">${session.wpm} WPM</span>
            </div>
            <p>${Math.floor(session.duration_seconds / 60)}m ${session.duration_seconds % 60}s • ${session.total_words} words</p>
        `;
        
        sessionItem.addEventListener('click', () => showSessionDetails(session));
        container.appendChild(sessionItem);
    });
}

function setupHistoryListeners() {
    const searchButton = document.getElementById('search-history-button');
    if (searchButton) {
        searchButton.addEventListener('click', () => {
            const searchTerm = document.getElementById('history-search').value.toLowerCase();
            searchSpeechHistory(searchTerm);
        });
    }
    
    const sortSelect = document.getElementById('sort-history');
    if (sortSelect) {
        sortSelect.addEventListener('change', () => {
            sortSpeechHistory(sortSelect.value);
        });
    }
}

function searchSpeechHistory(searchTerm) {
    // In a real app, this would search through actual data from backend
    fetch(`/api/speech_history?search=${encodeURIComponent(searchTerm)}`)
        .then(response => response.json())
        .then(data => {
            if (data && data.success) {
                displaySpeechHistory(data.sessions);
            } else {
                // Search through demo data for development
                const allSessions = getDemoHistorySessions();
                const filteredSessions = allSessions.filter(session => {
                    const date = new Date(session.timestamp);
                    const dateStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
                    return dateStr.toLowerCase().includes(searchTerm) || 
                           session.transcript.toLowerCase().includes(searchTerm);
                });
                displaySpeechHistory(filteredSessions);
            }
        })
        .catch(error => {
            console.error('Error searching speech history:', error);
            // Search through demo data on error
            const allSessions = getDemoHistorySessions();
            const filteredSessions = allSessions.filter(session => {
                const date = new Date(session.timestamp);
                const dateStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
                return dateStr.toLowerCase().includes(searchTerm) || 
                       session.transcript.toLowerCase().includes(searchTerm);
            });
            displaySpeechHistory(filteredSessions);
        });
}

function sortSpeechHistory(sortOption) {
    const historyItems = Array.from(document.querySelectorAll('.history-item'));
    
    if (historyItems.length === 0) return;
    
    // Get the current sessions data
    // In a real app, you would re-fetch or maintain this data in a variable
    // Here we use demo data for demonstration
    let sessions = getDemoHistorySessions();
    
    // Apply sorting
    switch (sortOption) {
        case 'date-desc':
            sessions.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            break;
        case 'date-asc':
            sessions.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            break;
        case 'duration-desc':
            sessions.sort((a, b) => b.duration_seconds - a.duration_seconds);
            break;
        case 'duration-asc':
            sessions.sort((a, b) => a.duration_seconds - b.duration_seconds);
            break;
    }
    
    displaySpeechHistory(sessions);
}

function showSessionDetails(session) {
    // Update details panel
    const detailsContainer = document.getElementById('speech-details-container');
    
    if (!detailsContainer) return;
    
    const date = new Date(session.timestamp);
    const formattedDate = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
    
    detailsContainer.innerHTML = `
        <h3>Speech Details</h3>
        <div class="detail-row">
            <span class="detail-label">Date:</span>
            <span class="detail-value">${formattedDate}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Duration:</span>
            <span class="detail-value">${Math.floor(session.duration_seconds / 60)}m ${session.duration_seconds % 60}s</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Total Words:</span>
            <span class="detail-value">${session.total_words}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Words Per Minute:</span>
            <span class="detail-value">${session.wpm}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Filler Words:</span>
            <span class="detail-value">${session.filler_count}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Posture:</span>
            <span class="detail-value">${session.final_posture || 'Not recorded'}</span>
        </div>
        <h4>Transcript</h4>
        <div class="transcript-box">
            ${session.transcript || 'No transcript available.'}
        </div>
    `;
    
    // Update analytics charts
    updateAnalyticsCharts(session);
    
    // Highlight the selected item
    document.querySelectorAll('.history-item').forEach(item => {
        item.classList.remove('selected');
    });
    
    const selectedItem = document.querySelector(`.history-item[data-session-id="${session.session_id}"]`);
    if (selectedItem) {
        selectedItem.classList.add('selected');
    }
}

function updateAnalyticsCharts(session) {
    // Get previous sessions for comparison (in a real app, fetch this from backend)
    const previousSessions = getDemoHistorySessions().filter(s => 
        new Date(s.timestamp) < new Date(session.timestamp)
    ).slice(0, 5);
    
    // Add current session for the chart
    const sessionsForChart = [...previousSessions, session].sort((a, b) => 
        new Date(a.timestamp) - new Date(b.timestamp)
    );
    
    // Create WPM chart
    const wpmCtx = document.getElementById('wpm-chart').getContext('2d');
    if (window.wpmChart) {
        window.wpmChart.destroy();
    }
    
    window.wpmChart = new Chart(wpmCtx, {
        type: 'line',
        data: {
            labels: sessionsForChart.map(s => {
                const date = new Date(s.timestamp);
                return date.getMonth() + 1 + '/' + date.getDate();
            }),
            datasets: [{
                label: 'Words Per Minute',
                data: sessionsForChart.map(s => s.wpm),
                borderColor: 'rgba(75, 192, 192, 1)',
                tension: 0.1,
                fill: false
            }]
        },
        options: {
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
    
    // Create Filler Words chart
    const fillerCtx = document.getElementById('filler-chart').getContext('2d');
    if (window.fillerChart) {
        window.fillerChart.destroy();
    }
    
    window.fillerChart = new Chart(fillerCtx, {
        type: 'bar',
        data: {
            labels: sessionsForChart.map(s => {
                const date = new Date(s.timestamp);
                return date.getMonth() + 1 + '/' + date.getDate();
            }),
            datasets: [{
                label: 'Filler Word Count',
                data: sessionsForChart.map(s => s.filler_count),
                backgroundColor: 'rgba(153, 102, 255, 0.6)'
            }]
        },
        options: {
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

function getDemoHistorySessions() {
    // Demo data for development and testing
    return [
        {
            session_id: 1,
            timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24 * 7).toISOString(), // 1 week ago
            duration_seconds: 180,
            total_words: 435,
            wpm: 145,
            filler_count: 12,
            final_posture: 'Poor',
            transcript: 'This is my first attempt at public speaking. I am a bit nervous but I will try my best to communicate effectively.'
        },
        {
            session_id: 2,
            timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24 * 5).toISOString(), // 5 days ago
            duration_seconds: 205,
            total_words: 512,
            wpm: 150,
            filler_count: 9,
            final_posture: 'Fair',
            transcript: 'Today I want to talk about climate change and its effects on our planet. This is an important topic that requires immediate attention.'
        },
        {
            session_id: 3,
            timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24 * 2).toISOString(), // 2 days ago
            duration_seconds: 240,
            total_words: 680,
            wpm: 170,
            filler_count: 5,
            final_posture: 'Good',
            transcript: 'Effective communication is the cornerstone of successful relationships, both personal and professional. Today I will share some strategies for improving your communication skills.'
        },
        {
            session_id: 4,
            timestamp: new Date().toISOString(), // Today
            duration_seconds: 137,
            total_words: 382,
            wpm: 167,
            filler_count: 3,
            final_posture: 'Good',
            transcript: 'I want to discuss the importance of public speaking. Being able to communicate effectively is crucial in both personal and professional settings.'
        }
    ];
}

// Notes Page Functions
function loadSavedNotecards() {
    const container = document.getElementById('notecards-container');

    console.log('Loading saved notecards...');
    displayNotecards(getDemoNotecards());
    setupNotecardsListeners();

    // In a real application, this would fetch from your Python backend
    fetch('/api/notecards')
        .then(response => response.json())
        .then(data => {
            if (data && data.success && Array.isArray(data.notecards) && data.notecards.length > 0) {
                displayNotecards(data.notecards);
                setupNotecardsListeners();
            } else {
                // Show demo data if no notecards are available
                displayNotecards(getDemoNotecards());
                setupNotecardsListeners();
            }
        })
        .catch(error => {
            console.error('Error fetching notecards:', error);
            displayNotecards(getDemoNotecards());
            setupNotecardsListeners();
        });
}

function displayNotecards(notecards) {
    const container = document.getElementById('notecards-container');
    container.innerHTML = '';
    
    if (!notecards || notecards.length === 0) {
        const emptyMessage = document.createElement('p');
        emptyMessage.textContent = 'No saved notecards found. Create a new notecard to get started!';
        container.appendChild(emptyMessage);
        return;
    }
    
    notecards.forEach(notecard => {
        const notecardElement = document.createElement('div');
        notecardElement.className = 'notecard-item';
        notecardElement.dataset.noteId = notecard.id;
        
        notecardElement.innerHTML = `
            <h3>${notecard.title}</h3>
            <p>${notecard.content.substring(0, 100)}${notecard.content.length > 100 ? '...' : ''}</p>
            <div class="notecard-tags">
                ${notecard.tags.map(tag => `<span class="tag">${tag}</span>`).join('')}
            </div>
        `;
        
        notecardElement.addEventListener('click', () => loadNotecardInEditor(notecard));
        container.appendChild(notecardElement);
    });
}

function setupNotecardsListeners() {
    const searchButton = document.getElementById('search-button');
    if (searchButton) {
        searchButton.addEventListener('click', () => {
            const searchTerm = document.getElementById('notecard-search').value.toLowerCase();
            searchNotecards(searchTerm);
        });
    }
    
    const newButton = document.getElementById('new-notecard');
    if (newButton) {
        newButton.addEventListener('click', createNewNotecard);
    }
    
    const saveButton = document.getElementById('save-notecard');
    if (saveButton) {
        saveButton.addEventListener('click', saveNotecard);
    }
    
    const deleteButton = document.getElementById('delete-notecard');
    if (deleteButton) {
        deleteButton.addEventListener('click', deleteNotecard);
    }
    
    // Set up tags input
    const tagsInput = document.getElementById('notecard-tags');
    if (tagsInput) {
        tagsInput.addEventListener('keydown', function(event) {
            if (event.key === 'Enter' || event.key === ',') {
                event.preventDefault();
                const tagText = this.value.trim();
                if (tagText) {
                    addTag(tagText);
                    this.value = '';
                }
            }
        });
    }
}

function loadNotecardInEditor(notecard) {
    document.getElementById('notecard-title').value = notecard.title;
    document.getElementById('notecard-content').value = notecard.content;
    
    // Set the current notecard ID
    document.getElementById('notecard-content').dataset.noteId = notecard.id;
    
    // Display tags
    const tagsDisplay = document.getElementById('tags-display');
    tagsDisplay.innerHTML = '';
    
    notecard.tags.forEach(tag => {
        addTagToDisplay(tag);
    });
    
    // Highlight the selected notecard
    document.querySelectorAll('.notecard-item').forEach(item => {
        item.classList.remove('selected');
    });
    
    const selectedItem = document.querySelector(`.notecard-item[data-note-id="${notecard.id}"]`);
    if (selectedItem) {
        selectedItem.classList.add('selected');
    }
}

function createNewNotecard() {
    document.getElementById('notecard-title').value = '';
    document.getElementById('notecard-content').value = '';
    document.getElementById('notecard-content').dataset.noteId = '';
    document.getElementById('tags-display').innerHTML = '';
    
    // Remove selected class from all notecards
    document.querySelectorAll('.notecard-item').forEach(item => {
        item.classList.remove('selected');
    });
}

function saveNotecard() {
    const title = document.getElementById('notecard-title').value;
    const content = document.getElementById('notecard-content').value;
    const noteId = document.getElementById('notecard-content').dataset.noteId;
    
    // Get tags
    const tags = Array.from(document.querySelectorAll('#tags-display .tag')).map(
        tag => tag.textContent.replace('×', '').trim()
    );
    
    if (!title || !content) {
        alert('Please enter a title and content for your notecard.');
        return;
    }
    
    // In a real app, this would send data to your backend
    const saveData = {
        id: noteId || Date.now().toString(),
        title,
        content,
        tags
    };
    
    console.log('Saving notecard:', saveData);
    
    // For demo purposes, we'll just update the UI
    // In a real app, this would be handled by the backend response
    if (noteId) {
        // Update existing notecard
        const existingCard = document.querySelector(`.notecard-item[data-note-id="${noteId}"]`);
        if (existingCard) {
            existingCard.querySelector('h3').textContent = title;
            existingCard.querySelector('p').textContent = content.substring(0, 100) + (content.length > 100 ? '...' : '');
            
            const tagsContainer = existingCard.querySelector('.notecard-tags');
            tagsContainer.innerHTML = tags.map(tag => `<span class="tag">${tag}</span>`).join('');
        }
    } else {
        // Add new notecard to display
        const notecards = getDemoNotecards();
        const newNotecard = {
            id: saveData.id,
            title: saveData.title,
            content: saveData.content,
            tags: saveData.tags
        };
        
        notecards.push(newNotecard);
        displayNotecards(notecards);
        
        // Set the ID in the editor
        document.getElementById('notecard-content').dataset.noteId = saveData.id;
    }
    
    alert('Notecard saved successfully!');
}

function deleteNotecard() {
    const noteId = document.getElementById('notecard-content').dataset.noteId;
    
    if (!noteId) {
        alert('No notecard selected to delete.');
        return;
    }
    
    if (!confirm('Are you sure you want to delete this notecard?')) {
        return;
    }
    
    // In a real app, this would send a delete request to your backend
    console.log('Deleting notecard:', noteId);
    
    // For demo purposes, we'll just update the UI
    const notecardElement = document.querySelector(`.notecard-item[data-note-id="${noteId}"]`);
    if (notecardElement) {
        notecardElement.remove();
    }
    
    createNewNotecard(); // Clear the editor
    
    alert('Notecard deleted successfully!');
}

function searchNotecards(searchTerm) {
    if (!searchTerm) {
        loadSavedNotecards();
        return;
    }
    
    // In a real app, this would search through actual data from backend
    // For demo, we'll filter the demo data
    const allNotecards = getDemoNotecards();
    const filteredNotecards = allNotecards.filter(notecard => 
        notecard.title.toLowerCase().includes(searchTerm) || 
        notecard.content.toLowerCase().includes(searchTerm) ||
        notecard.tags.some(tag => tag.toLowerCase().includes(searchTerm))
    );
    
    displayNotecards(filteredNotecards);
}

function addTag(tagText) {
    // Check if tag already exists
    const existingTags = Array.from(document.querySelectorAll('#tags-display .tag')).map(
        tag => tag.textContent.trim().toLowerCase()
    );
    
    if (existingTags.includes(tagText.toLowerCase())) {
        return;
    }
    
    addTagToDisplay(tagText);
}

function addTagToDisplay(tagText) {
    const tagsDisplay = document.getElementById('tags-display');
    
    const tagElement = document.createElement('span');
    tagElement.className = 'tag';
    tagElement.textContent = tagText;
    
    const removeButton = document.createElement('span');
    removeButton.className = 'remove-tag';
    removeButton.textContent = '×';
    removeButton.addEventListener('click', function(event) {
        event.stopPropagation();
        tagElement.remove();
    });
    
    tagElement.appendChild(removeButton);
    tagsDisplay.appendChild(tagElement);
}

function getDemoNotecards() {
    // Demo data for development and testing
    return [
        {
            id: '1',
            title: 'Public Speaking Tips',
            content: 'Make eye contact with the audience. Use gestures to emphasize points. Speak clearly and at a moderate pace. Practice your speech multiple times before presenting.',
            tags: ['tips', 'public speaking']
        },
        {
            id: '2',
            title: 'Handling Nervousness',
            content: 'Deep breathing exercises can help calm nerves. Visualize success before going on stage. Remember that most physical signs of nervousness aren\'t visible to the audience.',
            tags: ['anxiety', 'techniques']
        },
        {
            id: '3',
            title: 'Speech Structure',
            content: 'Introduction: Tell them what you\'re going to tell them. Body: Tell them. Conclusion: Tell them what you told them. Use transitions between main points for a smooth flow.',
            tags: ['structure', 'organization']
        }
    ];
}

// Home Page Functions
function initHomePage() {
    console.log('Home page initialized');
    loadRecentStats();
}

function loadRecentStats() {
    // In a real application, this would fetch from your Python backend
    fetch('/api/recent_stats')
        .then(response => response.json())
        .then(data => {
            if (data && data.success) {
                updateHomePageStats(data.stats);
            } else {
                // Show demo data if no stats are available
                updateHomePageStats(getDemoHomeStats());
            }
        })
        .catch(error => {
            console.error('Error fetching recent stats:', error);
            updateHomePageStats(getDemoHomeStats());
        });
}

function updateHomePageStats(stats) {
    // This function would update UI elements on the home page
    console.log('Home page stats:', stats);
    
    // If home page elements exist, update them
    const totalSessionsElement = document.getElementById('total-sessions');
    if (totalSessionsElement) {
        totalSessionsElement.textContent = stats.totalSessions;
    }
    
    const averageWpmElement = document.getElementById('average-wpm');
    if (averageWpmElement) {
        averageWpmElement.textContent = stats.averageWpm;
    }
    
    const totalPracticeTimeElement = document.getElementById('total-practice-time');
    if (totalPracticeTimeElement) {
        totalPracticeTimeElement.textContent = formatDuration(stats.totalPracticeTime);
    }
    
    // If we have a chart element, update the progress chart
    const progressChartElement = document.getElementById('progress-chart');
    if (progressChartElement) {
        updateProgressChart(progressChartElement, stats.sessionHistory);
    }
}

function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    
    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else {
        return `${minutes}m`;
    }
}

function updateProgressChart(canvas, sessionHistory) {
    const ctx = canvas.getContext('2d');
    if (window.progressChart) {
        window.progressChart.destroy();
    }
    
    window.progressChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: sessionHistory.map(s => {
                const date = new Date(s.timestamp);
                return date.getMonth() + 1 + '/' + date.getDate();
            }),
            datasets: [
                {
                    label: 'WPM',
                    data: sessionHistory.map(s => s.wpm),
                    borderColor: 'rgba(75, 192, 192, 1)',
                    yAxisID: 'y',
                    tension: 0.1
                },
                {
                    label: 'Filler Words',
                    data: sessionHistory.map(s => s.filler_count),
                    borderColor: 'rgba(153, 102, 255, 1)',
                    yAxisID: 'y1',
                    tension: 0.1
                }
            ]
        },
        options: {
            scales: {
                y: {
                    beginAtZero: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Words Per Minute'
                    }
                },
                y1: {
                    beginAtZero: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Filler Words'
                    },
                    grid: {
                        drawOnChartArea: false
                    }
                }
            }
        }
    });
}

function getDemoHomeStats() {
    // Demo data for development and testing
    return {
        totalSessions: 12,
        averageWpm: 162,
        totalPracticeTime: 2340, // seconds
        improvementRate: 8.5, // percent
        sessionHistory: [
            {
                timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24 * 30).toISOString(),
                wpm: 132,
                filler_count: 15
            },
            {
                timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24 * 25).toISOString(),
                wpm: 138,
                filler_count: 12
            },
            {
                timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24 * 20).toISOString(),
                wpm: 145,
                filler_count: 10
            },
            {
                timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24 * 15).toISOString(),
                wpm: 151,
                filler_count: 9
            },
            {
                timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24 * 10).toISOString(),
                wpm: 158,
                filler_count: 7
            },
            {
                timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24 * 5).toISOString(),
                wpm: 165,
                filler_count: 5
            },
            {
                timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24 * 1).toISOString(),
                wpm: 170,
                filler_count: 4
            }
        ]
    };
}