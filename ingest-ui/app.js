/**
 * Mukthi Guru Ingestion Portal
 *
 * Submits URLs to the backend /api/ingest endpoint with tag multi-select.
 * Polls /api/ingest/status for active ingestion progress.
 */
(function () {
  "use strict";

  const API_BASE = "";
  const INGEST_URL = `${API_BASE}/api/ingest`;
  const STATUS_URL = `${API_BASE}/api/ingest/status`;

  const form = document.getElementById("ingest-form");
  const urlInput = document.getElementById("url");
  const tagsSelect = document.getElementById("tags");
  const maxAccuracyCheckbox = document.getElementById("max-accuracy");
  const submitBtn = document.getElementById("submit-btn");
  const statusBox = document.getElementById("status");
  const progress = document.getElementById("progress");
  const progressBar = document.getElementById("progress-bar");
  const runsList = document.getElementById("runs-list");
  const refreshBtn = document.getElementById("refresh-btn");

  function getSelectedTags() {
    return Array.from(tagsSelect.selectedOptions).map((opt) => opt.value);
  }

  function setStatus(message, type = "info") {
    statusBox.textContent = message;
    statusBox.className = `status ${type}`;
  }

  function setProgress(percent) {
    const value = Math.max(0, Math.min(100, Math.round(percent * 100)));
    progress.hidden = false;
    progressBar.style.width = `${value}%`;
    progressBar.textContent = value > 0 ? `${value}%` : "";
    progressBar.setAttribute("aria-valuenow", String(value));
  }

  function resetProgress() {
    progress.hidden = true;
    progressBar.style.width = "0%";
    progressBar.textContent = "";
  }

  async function submitIngestion(event) {
    event.preventDefault();
    const url = urlInput.value.trim();
    const tags = getSelectedTags();

    if (!url) {
      setStatus("Please enter a URL.", "error");
      return;
    }
    if (tags.length === 0) {
      setStatus("Please select at least one knowledge tag.", "error");
      return;
    }

    submitBtn.disabled = true;
    setStatus("Submitting ingestion job...", "info");
    resetProgress();

    const payload = {
      url,
      tags,
      max_accuracy: maxAccuracyCheckbox.checked,
    };

    try {
      const response = await fetch(INGEST_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });

      if (response.status === 401 || response.status === 403) {
        setStatus("Authentication failed. Please log in as an admin first.", "error");
        return;
      }

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Server returned ${response.status}: ${text}`);
      }

      const data = await response.json();
      setStatus(`Ingestion started: ${data.message || url}`, "success");
      urlInput.value = "";
      setTimeout(loadStatus, 500);
    } catch (err) {
      setStatus(`Failed to start ingestion: ${err.message}`, "error");
    } finally {
      submitBtn.disabled = false;
    }
  }

  async function loadStatus() {
    try {
      const response = await fetch(STATUS_URL, { credentials: "same-origin" });
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          runsList.innerHTML =
            "<li class='run-item'>Authentication required. Please log in as admin.</li>";
          return;
        }
        throw new Error(`Server returned ${response.status}`);
      }

      const data = await response.json();
      const items = data.ingestions || data.items || data || [];
      renderRuns(Array.isArray(items) ? items : []);
    } catch (err) {
      runsList.innerHTML = `<li class='run-item error'>Unable to load status: ${err.message}</li>`;
    }
  }

  function renderRuns(items) {
    runsList.innerHTML = "";
    if (items.length === 0) {
      runsList.innerHTML = "<li class='run-item'>No active or recent ingestions.</li>";
      return;
    }

    for (const item of items) {
      const li = document.createElement("li");
      li.className = "run-item";
      const url = item.url || "unknown";
      const pct = Math.round((item.progress || 0) * 100);
      const status = item.status || "pending";
      const tags = Array.isArray(item.tags) ? item.tags.join(", ") : "general";
      li.innerHTML = `
        <div class="run-meta">
          <strong>${escapeHtml(url)}</strong>
          <span class="tag status-${escapeHtml(status)}">${escapeHtml(status)}</span>
        </div>
        <div class="run-tags">Tags: ${escapeHtml(tags)}</div>
        <div class="run-progress">
          <div class="run-progress-bar" style="width: ${pct}%"></div>
        </div>
        <div class="run-detail">${pct}% — ${escapeHtml(item.message || "")}</div>
      `;
      runsList.appendChild(li);
    }
  }

  function escapeHtml(text) {
    if (text == null) return "";
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  form.addEventListener("submit", submitIngestion);
  refreshBtn.addEventListener("click", loadStatus);

  loadStatus();
  setInterval(loadStatus, 10000);
})();
