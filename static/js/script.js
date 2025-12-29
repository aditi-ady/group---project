

async function generateSummary() {
    const urlInput = document.getElementById('youtubeURL');
    const url = urlInput.value.trim();
    if (!url) { alert("Please enter a YouTube URL!"); return; }

    toggleLoader(true);

    try {
        const response = await fetch('/api/summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });
        const data = await response.json();

        if (response.ok) {
            renderResults(data);
        } else {
            alert("Error: " + (data.error || "Failed"));
        }
    } catch (error) {
        alert("Something went wrong!");
    } finally {
        toggleLoader(false);
    }
}

function toggleLoader(show) {
    const ids = ['btnText', 'btnLoader', 'loadingSection', 'resultSection'];
    const display = show ? ['add', 'remove', 'remove', 'add'] : ['remove', 'add', 'add', 'remove'];
    
    document.getElementById('btnText').classList[display[0]]('d-none');
    document.getElementById('btnLoader').classList[display[1]]('d-none');
    document.getElementById('loadingSection').classList[display[2]]('d-none');
    if (!show) document.getElementById('resultSection').classList.remove('d-none');
}

function renderResults(data) {
    document.getElementById('videoTitle').innerText = data.title;
    document.getElementById('summaryContent').innerHTML = data.summary; 

    const quizBox = document.getElementById('quizContent');
    quizBox.innerHTML = ''; 

    if (data.quiz && data.quiz.length > 0) {
        data.quiz.forEach((q, index) => {
            let optionsHTML = '';
            q.options.forEach(opt => {
                
                optionsHTML += `<button class="btn btn-outline-light btn-sm w-100 mb-2 text-start" 
                    onclick="checkAnswer(this, '${opt}', '${q.answer}', '${data.subject || 'General'}')">${opt}</button>`;
            });
            quizBox.innerHTML += `<div class="mb-4"><p class="fw-bold mb-2">${index + 1}. ${q.question}</p>${optionsHTML}</div>`;
        });
    } else {
        quizBox.innerHTML = '<p class="text-muted">No quiz generated.</p>';
    }
}



async function updateServerStats(isCorrect, subject) {
    try {
        await fetch('/api/update_quiz_stats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ correct: isCorrect, subject: subject })
        });
        console.log("Stats updated for subject:", subject);
    } catch (error) {
        console.error("Failed to update stats", error);
    }
}


function checkAnswer(btn, selected, correct, subject) {
    if (selected === correct) {
        btn.classList.remove('btn-outline-light');
        btn.classList.add('btn-success');
        alert("✅ Correct!");
        updateServerStats(true, subject); 
    } else {
        btn.classList.remove('btn-outline-light');
        btn.classList.add('btn-danger');
        alert("❌ Wrong!");
        updateServerStats(false, subject); 
    }
}




function handleEnter(event) {
    if (event.key === "Enter") sendMessage();
}

async function sendMessage() {
    const inputField = document.getElementById('user-input');
    const message = inputField.value.trim();
    if (message === "") return;

    appendMessage('You', message, 'end');
    inputField.value = ''; 
    const loadingId = appendLoading();
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });
        const data = await response.json();
        document.getElementById(loadingId).remove();

        if (data.type === 'quiz') {
            appendQuiz(data.questions, data.subject);
        } else {
            appendMessage('AI Tutor', data.reply, 'start');
        }
    } catch (error) {
        document.getElementById(loadingId).remove();
        appendMessage('System', 'Error connecting to AI.', 'start');
    }
}

function appendMessage(sender, text, align) {
    const chatBox = document.getElementById('chat-box');
    const isUser = sender === 'You';
    const msgHTML = `
        <div class="d-flex flex-row justify-content-${isUser ? 'end' : 'start'} mb-3">
            <div class="p-3 text-white rounded-3 shadow-sm" style="background: ${isUser ? '#4e54c8' : 'rgba(255,255,255,0.1)'}; max-width: 80%;">
                <span class="fw-bold ${isUser ? 'text-info' : 'text-warning'} small">${sender}</span><br>
                ${text ? text.replace(/\n/g, '<br>') : ''}
            </div>
        </div>`;
    chatBox.insertAdjacentHTML('beforeend', msgHTML);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function appendQuiz(questions, subject) {
    const chatBox = document.getElementById('chat-box');
    
    questions.forEach((q, index) => {
        let optionsHTML = '';
        q.options.forEach(opt => {
            optionsHTML += `
                <button class="btn btn-outline-light btn-sm w-100 mb-2 text-start quiz-opt" 
                    onclick="checkChatQuiz(this, '${opt}', '${q.answer}', '${subject || 'General'}')">
                    ${opt}
                </button>
            `;
        });

        const quizHTML = `
            <div class="d-flex flex-row justify-content-start mb-4">
                <div class="p-4 text-white rounded-3 shadow border border-warning" style="background: rgba(0,0,0,0.4); max-width: 85%; width: 100%;">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <span class="fw-bold text-warning"><i class="fa-solid fa-brain"></i> Pop Quiz (${subject || 'General'})</span>
                        <span class="badge bg-danger">Q${index + 1}</span>
                    </div>
                    <p class="fw-bold mb-3">${q.question}</p>
                    ${optionsHTML}
                </div>
            </div>
        `;
        chatBox.insertAdjacentHTML('beforeend', quizHTML);
    });
    chatBox.scrollTop = chatBox.scrollHeight;
}

function checkChatQuiz(btn, selected, correct, subject) {
    const parentDiv = btn.parentElement; 
    const allBtns = parentDiv.querySelectorAll('.quiz-opt');
    allBtns.forEach(b => b.disabled = true);

    if (selected === correct) {
        btn.classList.remove('btn-outline-light');
        btn.classList.add('btn-success');
        btn.innerHTML += ' <i class="fa-solid fa-check"></i>';
        updateServerStats(true, subject); 
    } else {
        btn.classList.remove('btn-outline-light');
        btn.classList.add('btn-danger');
        btn.innerHTML += ' <i class="fa-solid fa-xmark"></i>';
        updateServerStats(false, subject); 
        
        allBtns.forEach(b => {
            if (b.innerText.includes(correct)) {
                b.classList.remove('btn-outline-light');
                b.classList.add('btn-success');
            }
        });
    }
}

function appendLoading() {
    const chatBox = document.getElementById('chat-box');
    const id = 'loading-' + Date.now();
    const loadingHTML = `...`; 
   
    const lHTML = `<div id="${id}" class="mb-3 text-white">Thinking...</div>`;
    chatBox.insertAdjacentHTML('beforeend', lHTML);
    chatBox.scrollTop = chatBox.scrollHeight;
    return id;
}
