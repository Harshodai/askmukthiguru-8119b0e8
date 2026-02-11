/**
 * Mukthi Guru — Ingestion Portal App
 *
 * Handles:
 * - URL submission to /api/ingest
 * - Health check polling
 * - Ingestion history (session)
 */

// === Configuration ===
// We are served from /ingest and API is at /api
// So access API relative to root
const API_BASE = ''; // Browsers resolve '/api/...' relative to current origin

const HEALTH_POLL_INTERVAL = 15000; // 15s

// === State ===
let history = [];
let isSubmitting = false;
let healthFailures = 0; // Track consecutive failures

// === DOM References ===
const elements = {
  form: document.getElementById('ingestForm'),
  urlInput: document.getElementById('urlInput'),
  submitBtn: document.getElementById('submitBtn'),
  statusBanner: document.getElementById('statusBanner'),
  statusIcon: document.getElementById('statusIcon'),
  statusMessage: document.getElementById('statusMessage'),
  statusDetail: document.getElementById('statusDetail'),
  healthBadge: document.getElementById('healthBadge'),
  healthDot: document.getElementById('healthDot'),
  healthText: document.getElementById('healthText'),
  totalChunks: document.getElementById('totalChunks'),
  serviceCount: document.getElementById('serviceCount'),
  systemStatus: document.getElementById('systemStatus'),
  historyList: document.getElementById('historyList'),
  historyEmpty: document.getElementById('historyEmpty'),
  historyCount: document.getElementById('historyCount'),
  maxAccuracyInput: document.getElementById('maxAccuracyInput'),
  progressContainer: document.getElementById('progressContainer'),
  progressBar: document.getElementById('progressBar'),
};

// === Health Check ===
async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(5000) });
    const data = await res.json();

    const isHealthy = data.status === 'healthy';
    elements.healthBadge.className = `health-badge ${isHealthy ? 'healthy' : 'degraded'}`;
    elements.healthText.textContent = isHealthy ? 'Healthy' : 'Degraded';

    // Update stats
    elements.totalChunks.textContent = data.total_chunks?.toLocaleString() || '0';
    const services = data.services || {};
    const onlineCount = Object.values(services).filter(v => v === true).length;
    elements.serviceCount.textContent = `${onlineCount}/${Object.keys(services).length}`;
    elements.systemStatus.textContent = isHealthy ? '✅' : '⚠️';

    // Reset failures
    healthFailures = 0;

  } catch (err) {
    healthFailures++;
    // Only show offline if 3 consecutive failures
    if (healthFailures >= 3) {
      elements.healthBadge.className = 'health-badge offline';
      elements.healthText.textContent = 'Offline';
      elements.totalChunks.textContent = '—';
      elements.serviceCount.textContent = '—';
      elements.systemStatus.textContent = '❌';
    }
  }
}

// === Progress Polling ===
async function pollProgress() {
  try {
    const res = await fetch(`${API_BASE}/api/ingest/status`);
    if (!res.ok) return;
    const data = await res.json();

    // Find active job (most recent processing)
    const jobs = Object.values(data);
    const processing = jobs.filter(j => j.status === 'processing').sort((a, b) => b.updated_at - a.updated_at)[0];

    if (processing) {
      // Update UI
      showStatus('processing', 'Ingesting...', processing.message);
      updateProgressBar(processing.progress);

      if (!isSubmitting) {
        // If we refreshed page, sync state
        isSubmitting = true;
        elements.submitBtn.disabled = true;
        elements.submitBtn.classList.add('loading');
      }
    } else if (isSubmitting) {
      // We were submitting, but no processing job found. Check for recent success/error.
      const recent = jobs.sort((a, b) => b.updated_at - a.updated_at)[0];
      if (recent && (Date.now() / 1000 - recent.updated_at < 10)) { // 10s window
        if (recent.status === 'success') {
          showStatus('success', 'Ingestion Complete!', recent.message);
          updateProgressBar(1.0);
          setTimeout(() => hideProgressBar(), 3000);
        } else {
          showStatus('error', 'Ingestion Failed', recent.message);
          hideProgressBar();
        }
      }
      isSubmitting = false;
      elements.submitBtn.disabled = false;
      elements.submitBtn.classList.remove('loading');
    }
  } catch (err) {
    console.error("Poll error", err);
  }
}

function updateProgressBar(pct) {
  elements.progressContainer.style.display = 'block';
  elements.progressBar.style.width = `${pct * 100}%`;
}

function hideProgressBar() {
  elements.progressContainer.style.display = 'none';
  elements.progressBar.style.width = '0%';
}

// === Status Banner ===
function showStatus(type, message, detail = '') {
  const icons = { success: '✅', error: '❌', processing: '⏳' };
  elements.statusBanner.className = `status-banner ${type}`;
  elements.statusIcon.textContent = icons[type] || '📋';
  elements.statusMessage.textContent = message;
  elements.statusDetail.textContent = detail;
}

function hideStatus() {
  elements.statusBanner.className = 'status-banner hidden';
}

// === History ===
function addHistoryItem(url, status, detail = '') {
  const item = { url, status, detail, time: new Date() };
  history.unshift(item);
  renderHistory();
}

function updateLastHistoryItem(status, detail) {
  if (history.length > 0) {
    history[0].status = status;
    history[0].detail = detail;
    renderHistory();
  }
}

function renderHistory() {
  elements.historyCount.textContent = history.length;

  if (history.length === 0) {
    elements.historyEmpty.style.display = 'block';
    // Remove only history-item elements, keep the empty message
    elements.historyList.querySelectorAll('.history-item').forEach(el => el.remove());
    return;
  }

  elements.historyEmpty.style.display = 'none';
  // Remove old items
  elements.historyList.querySelectorAll('.history-item').forEach(el => el.remove());

  history.forEach((item, i) => {
    const el = document.createElement('div');
    el.className = 'history-item';
    el.style.animationDelay = `${i * 0.05}s`;

    const icon = item.status === 'success' ? '🎬'
      : item.status === 'error' ? '⚠️'
        : '🔄';

    const timeStr = item.time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    el.innerHTML = `
      <span class="history-item-icon">${icon}</span>
      <div class="history-item-content">
        <div class="history-item-url" title="${escapeHtml(item.url)}">${escapeHtml(item.url)}</div>
        <div class="history-item-meta">${timeStr}${item.detail ? ' · ' + escapeHtml(item.detail) : ''}</div>
      </div>
      <span class="history-item-status ${item.status}">${item.status}</span>
    `;

    elements.historyList.appendChild(el);
  });
}

// === Form Submit ===
async function handleSubmit(e) {
  e.preventDefault();
  if (isSubmitting) return;

  const url = elements.urlInput.value.trim();
  const maxAccuracy = elements.maxAccuracyInput.checked;

  if (!url) return;

  // Validate URL format
  if (!isValidIngestUrl(url)) {
    showStatus('error', 'Invalid URL', 'Please enter a valid YouTube video, playlist, or image URL.');
    return;
  }

  isSubmitting = true;
  elements.submitBtn.classList.add('loading');
  elements.submitBtn.disabled = true;

  showStatus('processing', 'Ingestion started...', `Submitting: ${url}`);
  addHistoryItem(url, 'processing', 'Submitted');

  try {
    const res = await fetch(`${API_BASE}/api/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, max_accuracy: maxAccuracy }),
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || `HTTP ${res.status}`);
    }

    showStatus('success', 'Ingestion submitted!',
      `Status: ${data.status} — ${data.message || 'Processing in background...'}`);
    updateLastHistoryItem('success', data.message || 'Submitted');

    // Clear input
    elements.urlInput.value = '';

    // Refresh health after a delay (so we can see updated chunk count)
    setTimeout(checkHealth, 10000);
    setTimeout(checkHealth, 30000);
    setTimeout(checkHealth, 60000);

  } catch (err) {
    showStatus('error', 'Ingestion failed', err.message);
    updateLastHistoryItem('error', err.message);
  } finally {
    isSubmitting = false;
    elements.submitBtn.classList.remove('loading');
    elements.submitBtn.disabled = false;
  }
}

// === Validation ===
function isValidIngestUrl(url) {
  try {
    const u = new URL(url);
    // YouTube
    if (u.hostname.includes('youtube.com') || u.hostname.includes('youtu.be')) return true;
    // Image URL
    if (/\.(jpg|jpeg|png|gif|webp|bmp|tiff)(\?|$)/i.test(u.pathname)) return true;
    // Allow any URL for flexibility
    return true;
  } catch {
    return false;
  }
}

// === Utilities ===
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// === Init ===
function init() {
  elements.form.addEventListener('submit', handleSubmit);

  // Initial health check
  checkHealth();
  // Poll health
  setInterval(checkHealth, HEALTH_POLL_INTERVAL);

  // Poll progress (frequent)
  setInterval(pollProgress, 2000);

  // Focus input
  elements.urlInput.focus();
}

document.addEventListener('DOMContentLoaded', init);
