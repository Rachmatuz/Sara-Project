const chatInput = document.getElementById('chatInput');
const sendButton = document.getElementById('sendButton');
const chatMessages = document.getElementById('chatMessages');

sendButton.addEventListener('click', handleSend);
chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
});

let chatCount = 0;

// Load announcements on startup
async function loadAnnouncements() {
    try {
        const res = await fetch('/api/pengumuman');
        const data = await res.json();

        if(data.length > 0) {
            const latest = data[0];
            const banner = document.getElementById('announcementBanner');
            const text = document.getElementById('announcementText');

            const icon = latest.tipe === 'warning' ? '⚠️' : latest.tipe === 'success' ? '✅' : '📢';
            text.innerHTML = `${icon} <strong>${latest.judul}:</strong> ${latest.isi}`;
            banner.style.display = 'block';
        }
    } catch(e) {
        console.log('No announcements');
    }
}

function closeAnnouncement() {
    document.getElementById('announcementBanner').style.display = 'none';
}

async function handleSend() {
    const message = chatInput.value.trim();
    if (message === '') {
        chatInput.focus();
        return;
    }

    displayUserMessage(message);
    chatInput.value = '';
    chatInput.focus();

    const loadingBubble = showLoadingBubble();
    const startTime = Date.now();
    const minWaitTime = 1500;

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message }),
        });

        const data = await response.json();
        const elapsedTime = Date.now() - startTime;
        if (elapsedTime < minWaitTime) {
            await new Promise(resolve => setTimeout(resolve, minWaitTime - elapsedTime));
        }

        removeLoadingBubble(loadingBubble);

        if (response.ok && data.reply) {
            if (data.type === 'location') {
                displayLocationMessage(data);
            } else {
                displayBotMessage(data.reply);
            }
        } else {
            displayBotMessage(`❌ ${data.error || 'Error tidak diketahui'}`);
        }

    } catch (error) {
        removeLoadingBubble(loadingBubble);
        displayBotMessage(`❌ Koneksi error: ${error.message}`);
    }

    // Count chats and show survey after 5 messages
    chatCount++;
    if(chatCount === 5) {
        setTimeout(() => openModal('modalSurvey'), 2000);
    }
}

function displayUserMessage(text) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper user';
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = formatMessage(text);
    wrapper.appendChild(bubble);
    chatMessages.appendChild(wrapper);
    scrollToBottom();
}

function displayBotMessage(text) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper bot';
    const avatar = document.createElement('div');
    avatar.className = 'bot-avatar';
    avatar.textContent = '🤖';
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = formatMessage(text);
    wrapper.appendChild(avatar);
    wrapper.appendChild(bubble);
    chatMessages.appendChild(wrapper);
    scrollToBottom();
}

function displayLocationMessage(data) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper bot';
    const avatar = document.createElement('div');
    avatar.className = 'bot-avatar';
    avatar.textContent = '🤖';
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble location-bubble';
    bubble.innerHTML = `
        <p style="font-weight: bold; margin-bottom: 8px;">${escapeHtml(data.reply)}</p>
        <p style="font-size: 13px; color: #666; margin-bottom: 8px;">${escapeHtml(data.address)}</p>
        <div style="margin: 10px 0; padding: 10px; background: rgba(102, 126, 234, 0.1); border-radius: 8px; font-size: 12px;">
            ${escapeHtml(data.details)}
        </div>
        <a href="${data.maps_url}" target="_blank" rel="noopener noreferrer" class="maps-button">
            📍 Buka di Google Maps
        </a>
    `;
    wrapper.appendChild(avatar);
    wrapper.appendChild(bubble);
    chatMessages.appendChild(wrapper);
    scrollToBottom();
}

function showLoadingBubble() {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper bot';
    wrapper.id = 'loading-bubble';
    const avatar = document.createElement('div');
    avatar.className = 'bot-avatar';
    avatar.textContent = '🤖';
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'typing-indicator';
    loadingDiv.innerHTML = `<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>`;
    wrapper.appendChild(avatar);
    wrapper.appendChild(loadingDiv);
    chatMessages.appendChild(wrapper);
    scrollToBottom();
    return wrapper;
}

function removeLoadingBubble(loadingBubble) {
    if (loadingBubble && loadingBubble.parentNode) {
        loadingBubble.remove();
    }
}

function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatMessage(text) {
    return escapeHtml(text).replace(/\n/g, '<br>');
}

// Modal functions
function openModal(id) {
    document.getElementById(id).classList.add('active');
}
function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

// Close modal when clicking outside
window.addEventListener('click', (e) => {
    if(e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
    }
});

// Submit Cuti
async function submitCuti() {
    const data = {
        nama: document.getElementById('cutiNama').value,
        nip: document.getElementById('cutiNip').value,
        jenis_cuti: document.getElementById('cutiJenis').value,
        tanggal_mulai: document.getElementById('cutiMulai').value,
        tanggal_selesai: document.getElementById('cutiSelesai').value,
        alasan: document.getElementById('cutiAlasan').value
    };

    if(!data.nama || !data.nip || !data.tanggal_mulai || !data.tanggal_selesai) {
        alert('Mohon lengkapi semua field yang wajib diisi!');
        return;
    }

    const res = await fetch('/api/cuti', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });

    const result = await res.json();
    alert(result.message);
    closeModal('modalCuti');

    // Clear form
    document.getElementById('cutiNama').value = '';
    document.getElementById('cutiNip').value = '';
    document.getElementById('cutiMulai').value = '';
    document.getElementById('cutiSelesai').value = '';
    document.getElementById('cutiAlasan').value = '';
}

// Survey Rating
let currentRating = 5;
function setRating(n) {
    currentRating = n;
    document.getElementById('surveyRating').value = n;
    const stars = document.querySelectorAll('#starContainer span');
    stars.forEach((s, i) => {
        s.style.opacity = i < n ? '1' : '0.3';
        s.style.filter = i < n ? 'grayscale(0)' : 'grayscale(1)';
    });
}

// Submit Survey
async function submitSurvey() {
    const data = {
        nama: document.getElementById('surveyNama').value,
        rating: currentRating,
        saran: document.getElementById('surveySaran').value
    };

    const res = await fetch('/api/survey', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });

    const result = await res.json();
    alert(result.message);
    closeModal('modalSurvey');
}

// Init
window.addEventListener('load', () => {
    loadAnnouncements();

    fetch('/api/test')
        .then(res => res.json())
        .then(data => console.log('✅ Server OK:', data))
        .catch(err => console.error('❌ Server error:', err));

    setTimeout(() => {
        displayBotMessage('Halo! 👋 Saya SARA, asisten digital untuk PT Samaratu Daya Teknik. Apa yang bisa saya bantu?');
    }, 500);
});