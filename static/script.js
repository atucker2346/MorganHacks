document.addEventListener('DOMContentLoaded', function() {


    // --- Get References to Practice Page Elements FIRST ---
    // Moved these declarations to the top to prevent initialization errors
    const feedbackContentDiv = document.getElementById('feedback-content');
    const wpmValueSpan = document.getElementById('wpm-value');
    const pacingValueSpan = document.getElementById('pacing-value');
    const fillerCountSpan = document.getElementById('filler-count');
    const transcriptDisplay = document.getElementById('transcript-display');
    const tipsList = document.getElementById('tips-list');
    const notesListDiv = document.getElementById('notes-list');
    const saveButton = document.getElementById('saveSpeechButton');


    // --- Page Navigation Logic ---
    const navLinks = document.querySelectorAll('#main-nav a[data-page], .cta-button[data-page]');
    const pages = document.querySelectorAll('.page');
    const mainNav = document.getElementById('main-nav');


    function showPage(pageId, triggeredByClick = false) { // Add flag to know if it's a click
        console.log(">>> showPage called with:", pageId, "Clicked:", triggeredByClick);
        pages.forEach(page => page.classList.remove('active'));
        const targetPage = document.getElementById(pageId);


        if (targetPage) {
            targetPage.classList.add('active');
            // Fetch data when practice page is shown
            if (pageId === 'practice-page') {
                console.log(">>> Practice page detected, calling fetch...");
                fetchAndUpdatePracticeData();
            }
        } else {
            console.warn(`Page with ID "${pageId}" not found. Defaulting to home.`);
            const homePage = document.getElementById('home-page');
            if (homePage) homePage.classList.add('active'); // Default to home
            pageId = 'home-page'; // Ensure pageId reflects the actual page shown
        }


        // Update nav active state
        if (mainNav) {
             mainNav.querySelectorAll('a[data-page]').forEach(link => {
                 link.classList.remove('active');
                 if (link.getAttribute('data-page') === pageId) {
                    link.classList.add('active');
                 }
             });
         }


         // *** FIXED SCROLL LOGIC ***
         // Scroll to top unless it's the home page.
         if (pageId !== 'home-page') {
              // You could add more complex logic here using triggeredByClick if needed
              window.scrollTo(0, 0);
         }
    }


     navLinks.forEach(link => {
         link.addEventListener('click', function(event) {
             event.preventDefault();
             const pageId = this.getAttribute('data-page');
             const targetHref = this.getAttribute('href');
             if (pageId) {
                 // Pass true for triggeredByClick flag
                 showPage(pageId, true);
                 if (targetHref.startsWith('#') && document.getElementById(pageId)) {
                     history.pushState({page: pageId}, null, targetHref);
                 }
             } else if (targetHref === '#features') {
                  const featuresSection = document.querySelector('.features-section');
                  if (featuresSection) {
                      featuresSection.scrollIntoView({ behavior: 'smooth' });
                  }
             }
         });
     });


    // Handle back/forward navigation
    window.addEventListener('popstate', function(event) {
        let pageIdToShow = 'home-page';
        if (event.state && event.state.page) {
            pageIdToShow = event.state.page;
        } else {
            const hash = window.location.hash.substring(1);
            if (hash) {
                 const potentialPageId = hash + '-page';
                 if (document.getElementById(potentialPageId)) {
                     pageIdToShow = potentialPageId;
                 }
             }
        }
         // Pass false for triggeredByClick when using browser history
         showPage(pageIdToShow, false);
     });




    // --- Practice Page Specific Functions ---


    // Function to fetch data and update the practice page
    async function fetchAndUpdatePracticeData() {
        console.log("Fetching latest speech data...");
        setLoadingState(true); // Show loading indicators


        try {
            const response = await fetch('/botapi/get-latest/'); // Fetch from the correct endpoint
            if (!response.ok) {
                let errorMsg = `HTTP error! status: ${response.status}`;
                if (response.status === 404) errorMsg = "Error: Backend endpoint /botapi/get-latest/ not found (404). Check Django urls.py.";
                else if (response.status === 500) errorMsg = "Error: Server error (500). Check Django server logs for /botapi/get-latest/.";
                throw new Error(errorMsg);
            }
            const data = await response.json();
            console.log("Successfully fetched data:", data);


            // --- Update the HTML elements ---
            if (wpmValueSpan) wpmValueSpan.textContent = data.wpm ?? 'N/A';
            if (pacingValueSpan) pacingValueSpan.textContent = data.pacing ?? 'N/A';
            if (fillerCountSpan) fillerCountSpan.textContent = data.filler_count ?? 'N/A';
            if (transcriptDisplay) transcriptDisplay.value = data.transcript ?? 'No transcript available.';


            if (feedbackContentDiv) {
                 feedbackContentDiv.innerHTML = ''; // Clear previous
                 const speechP = document.createElement('p');
                 speechP.innerHTML = `<strong>Speech:</strong> ${data.feedback_speech || 'No speech feedback provided.'}`;
                 const postureP = document.createElement('p');
                 postureP.innerHTML = `<strong>Posture:</strong> ${data.feedback_posture || 'No posture feedback provided.'}`;
                 feedbackContentDiv.appendChild(speechP);
                 feedbackContentDiv.appendChild(postureP);
            }


            if (tipsList) {
                 tipsList.innerHTML = ''; // Clear previous
                 const combinedFeedback = `${data.feedback_speech || ''} ${data.feedback_posture || ''}`;
                 const potentialTips = combinedFeedback.split(/[.]+/g).map(tip => tip.trim()).filter(tip => tip.length > 10);
                 if (potentialTips.length > 0) {
                      potentialTips.forEach(tipText => {
                          const li = document.createElement('li');
                          li.textContent = tipText + '.';
                          tipsList.appendChild(li);
                      });
                 } else if (data.transcript && data.transcript !== 'N/A') { // Check if data was actually loaded
                     tipsList.innerHTML = '<li>Looks good! Keep practicing to refine further.</li>';
                 } else {
                      tipsList.innerHTML = '<li class="loading-block">No tips available yet.</li>';
                 }
            }


            if (notesListDiv) {
                 notesListDiv.innerHTML = ''; // Clear previous
                 if (data.notecards && Array.isArray(data.notecards) && data.notecards.length > 0 && data.notecards[0] !== 'N/A') {
                     data.notecards.forEach(noteText => {
                         if (noteText) {
                             const noteCard = document.createElement('div'); noteCard.className = 'note-card';
                             const noteIcon = document.createElement('div'); noteIcon.className = 'note-icon'; noteIcon.textContent = '📝';
                             const noteTextDiv = document.createElement('div'); noteTextDiv.className = 'note-text'; noteTextDiv.textContent = noteText;
                             noteCard.appendChild(noteIcon); noteCard.appendChild(noteTextDiv);
                             notesListDiv.appendChild(noteCard);
                         }
                     });
                 } else if (data.transcript && data.transcript !== 'N/A') { // Check if data was actually loaded
                    notesListDiv.innerHTML = '<p>No specific note cards generated for this session.</p>';
                 } else {
                    notesListDiv.innerHTML = '<p class="loading-block">No note cards available yet.</p>';
                 }
            }


        } catch (error) {
            console.error('Error fetching or updating speech data:', error);
            if (feedbackContentDiv) feedbackContentDiv.innerHTML = `<p style="color: #ff6b6b;">⚠️ Error loading feedback: ${error.message}</p>`;
            if (tipsList) tipsList.innerHTML = `<li style="color: #ff6b6b;">⚠️ Error loading tips</li>`;
            if (notesListDiv) notesListDiv.innerHTML = `<p style="color: #ff6b6b;">⚠️ Error loading notes</p>`;
            if (wpmValueSpan) wpmValueSpan.textContent = 'Err';
            if (pacingValueSpan) pacingValueSpan.textContent = 'Err';
            if (fillerCountSpan) fillerCountSpan.textContent = 'Err';
            if (transcriptDisplay) transcriptDisplay.value = `Error loading data: ${error.message}`;
        } finally {
             setLoadingState(false); // Hide loading indicators
        }
    }


    // Helper function to manage loading indicators
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
             // Keep save button disabled until feature is implemented
             // if (saveButton) saveButton.disabled = false;
         }
    }


    // Save button functionality (Placeholder)
     if (saveButton) {
         saveButton.addEventListener('click', function() {
             console.log('Save Speech button clicked! (Functionality not implemented)');
             showTemporaryMessage('Save Speech functionality is planned for a future update.');
         });
     }


    // --- Utility Function ---
    function showTemporaryMessage(message) {
        const existingMessage = document.getElementById('temp-message-box');
        if (existingMessage) existingMessage.remove();
        const messageDiv = document.createElement('div');
        messageDiv.id = 'temp-message-box';
        messageDiv.textContent = message;
        messageDiv.style.position = 'fixed'; messageDiv.style.bottom = '20px'; messageDiv.style.left = '50%'; messageDiv.style.transform = 'translateX(-50%)';
        messageDiv.style.backgroundColor = 'var(--primary-purple)'; messageDiv.style.color = 'var(--text-color)'; messageDiv.style.padding = '12px 25px';
        messageDiv.style.borderRadius = '8px'; messageDiv.style.zIndex = '1001'; messageDiv.style.opacity = '1';
        messageDiv.style.transition = 'opacity 0.5s ease-out 2.5s'; messageDiv.style.boxShadow = '0 3px 10px rgba(0,0,0,0.3)';
        document.body.appendChild(messageDiv);
        setTimeout(() => {
            messageDiv.style.opacity = '0';
            setTimeout(() => { if (messageDiv.parentNode) { messageDiv.remove(); } }, 500);
        }, 3000);
    }




     // --- Initial Page Load ---
     let initialPageId = 'home-page';
     if (window.history.state && window.history.state.page) {
          initialPageId = window.history.state.page;
     } else {
          const initialHash = window.location.hash.substring(1);
          if (initialHash) {
              const potentialPageId = initialHash + '-page';
              if (document.getElementById(potentialPageId)) initialPageId = potentialPageId;
          }
     }
      // Ensure the initial URL reflects the state
     if (window.location.hash !== `#${initialPageId.replace('-page', '')}` && initialPageId !== 'home-page') {
          history.replaceState({page: initialPageId}, null, `#${initialPageId.replace('-page', '')}`);
     } else if (initialPageId === 'home-page' && window.location.hash !== '#home' && window.location.hash !== '') {
          history.replaceState({page: 'home-page'}, null, '#home');
     }
      // Call showPage for the initial load, indicate it's not from a click
      showPage(initialPageId, false);


    console.log('Speech Analysis page setup complete.');
});