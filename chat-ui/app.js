const chatWindow = document.getElementById('chat-window');
const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');

let conversationHistory = [];

// Initialize
async function checkHealth() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        if (data.status === 'ok' || data.status === 'degraded') {
            statusDot.className = 'dot online';
            statusText.innerText = 'Mukthi Guru Online';
        } else {
            statusDot.className = 'dot busy';
            statusText.innerText = 'System Busy';
        }
    } catch (e) {
        statusDot.className = 'dot';
        statusText.innerText = 'Offline';
    }
}

function appendMessage(role, content, citations = []) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;
    
    let html = `<div class="content">${content}</div>`;
    
    if (citations && citations.length > 0) {
        html += `<div class="sources">`;
        citations.forEach((url, i) => {
            const domain = new URL(url).hostname.replace('www.', '');
            html += `<a href="${url}" target="_blank" class="source-tag">[Source ${i+1}: ${domain}]</a>`;
        });
        html += `</div>`;
    }
    
    msgDiv.innerHTML = html;
    chatWindow.appendChild(msgDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    return msgDiv;
}

function showTyping() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message guru typing-indicator';
    typingDiv.innerHTML = `
        <div class="typing">
            <span></span><span></span><span></span>
        </div>
    `;
    chatWindow.appendChild(typingDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    return typingDiv;
}

async function sendMessage(text) {
    if (!text.trim()) return;

    // Add user message to UI
    appendMessage('user', text);
    userInput.value = '';
    
    // Show typing
    const typingIndicator = showTyping();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                messages: conversationHistory,
                user_message: text,
                meditation_step: 0
            })
        });

        if (!response.ok) throw new Error('Guru is silent right now...');

        const data = await response.json();
        
        // Remove typing
        typingIndicator.remove();

        // Add Guru's message
        appendMessage('guru', data.response, data.citations);

        // Update history
        conversationHistory.push({ role: 'user', content: text });
        conversationHistory.push({ role: 'assistant', content: data.response });

        // Limit history for context window
        if (conversationHistory.length > 10) conversationHistory.shift();

    } catch (error) {
        typingIndicator.remove();
        appendMessage('system', `Error: ${error.message}`);
    }
}

chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    sendMessage(userInput.value);
});

// Start
checkHealth();
setInterval(checkHealth, 30000);
