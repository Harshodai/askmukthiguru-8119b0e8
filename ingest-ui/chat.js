const API_BASE = '';

const elements = {
    form: document.getElementById('chatForm'),
    input: document.getElementById('chatInput'),
    messages: document.getElementById('chatMessages'),
    sendBtn: document.getElementById('sendBtn'),
};

function addMessage(text, role) {
    const el = document.createElement('div');
    el.className = `message ${role}`;
    // Simple markdown-ish rendering
    let html = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
    el.innerHTML = html;

    elements.messages.appendChild(el);
    elements.messages.scrollTop = elements.messages.scrollHeight;
}

async function handleSubmit(e) {
    e.preventDefault();
    const query = elements.input.value.trim();
    if (!query) return;

    // Add User Message
    addMessage(query, 'user');
    elements.input.value = '';
    elements.input.style.height = '60px'; // Reset height
    elements.sendBtn.disabled = true;

    // Add generic loading placeholder
    const loadingId = 'loading-' + Date.now();
    const loadingEl = document.createElement('div');
    loadingEl.className = 'message system';
    loadingEl.id = loadingId;
    loadingEl.textContent = 'Thinking...';
    elements.messages.appendChild(loadingEl);

    try {
        const res = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: query, stream: false }), // No streaming for now
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();

        // Remove loading
        document.getElementById(loadingId).remove();

        // Add System Message
        addMessage(data.response, 'system');

    } catch (err) {
        document.getElementById(loadingId).remove();
        addMessage(`Error: ${err.message}`, 'system');
    } finally {
        elements.sendBtn.disabled = false;
        elements.input.focus();
    }
}

// Auto-resize textarea
elements.input.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

// Handle Enter to submit (Shift+Enter for new line)
elements.input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit(e);
    }
});

elements.form.addEventListener('submit', handleSubmit);
elements.input.focus();
