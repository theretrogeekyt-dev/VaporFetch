document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const form = document.getElementById('download-form');
  const appIdInput = document.getElementById('appId');
  const installDirInput = document.getElementById('installDir');
  const btnLookup = document.getElementById('btn-lookup');
  const previewCard = document.getElementById('game-preview');
  const previewImg = document.getElementById('preview-image');
  const previewName = document.getElementById('preview-name');
  const previewAppId = document.getElementById('preview-appid');
  const presetChips = document.getElementById('preset-chips');
  const credentialsBox = document.getElementById('account-credentials');
  const authRadios = document.querySelectorAll('input[name="authMode"]');
  const btnSubmit = document.getElementById('btn-submit');
  const btnCancel = document.getElementById('btn-cancel');
  const nasStorageChip = document.getElementById('nas-storage-chip');
  const storageText = document.getElementById('storage-text');
  const globalBadge = document.getElementById('global-status-badge');
  const globalBadgeText = document.getElementById('global-status-text');

  // Dashboard & Terminal
  const dashAppName = document.getElementById('dash-app-name');
  const dashStage = document.getElementById('dash-stage');
  const dashSpeed = document.getElementById('dash-speed');
  const dashSize = document.getElementById('dash-size');
  const progressFill = document.getElementById('progress-fill');
  const progressPercent = document.getElementById('progress-percent');
  const progressDesc = document.getElementById('progress-status-desc');
  const terminal = document.getElementById('terminal');
  const btnAutoscroll = document.getElementById('btn-autoscroll');
  const btnCopyLogs = document.getElementById('btn-copy-logs');
  const btnClearLogs = document.getElementById('btn-clear-logs');
  const historyTableBody = document.getElementById('history-table-body');
  const btnClearHistory = document.getElementById('btn-clear-history');

  // Modal
  const modal = document.getElementById('steamguard-modal');
  const modalInput = document.getElementById('modal-guard-code');
  const btnModalSubmit = document.getElementById('modal-submit-code');
  const btnModalCancel = document.getElementById('modal-cancel-download');

  let autoScroll = true;
  let eventSource = null;
  let activeAppId = null;

  // Initialize
  initSSE();
  fetchStorage();
  fetchPresets();
  fetchHistory();

  // Auth toggle
  authRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      if (radio.value === 'account') {
        credentialsBox.classList.remove('hidden');
      } else {
        credentialsBox.classList.add('hidden');
      }
    });
  });

  // AppID Lookup on blur / inspect
  btnLookup.addEventListener('click', () => lookupApp(appIdInput.value));
  appIdInput.addEventListener('change', () => {
    if (appIdInput.value.trim()) {
      lookupApp(appIdInput.value);
    }
  });

  async function lookupApp(appId) {
    const id = String(appId).trim();
    if (!id || !/^\d+$/.test(id)) return;

    try {
      btnLookup.disabled = true;
      btnLookup.textContent = '...';
      const res = await fetch(`/api/appinfo/${id}`);
      const data = await res.json();

      if (data && data.success) {
        previewImg.src = data.headerImage;
        previewName.textContent = data.name;
        previewAppId.textContent = `${data.appId}${data.isFree ? ' • Anonymous Supported' : ''}`;
        previewCard.classList.remove('hidden');

        // Suggest install dir if currently empty
        if (!installDirInput.value.trim()) {
          const suggested = (data.name || id)
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, '');
          installDirInput.value = suggested;
        }
      }
    } catch (e) {
      console.warn('App lookup error:', e);
    } finally {
      btnLookup.disabled = false;
      btnLookup.textContent = 'Inspect';
    }
  }

  // Fetch Presets
  async function fetchPresets() {
    try {
      const res = await fetch('/api/presets');
      const presets = await res.json();
      presetChips.innerHTML = '';

      presets.forEach(preset => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'preset-chip';
        chip.textContent = preset.name;
        chip.addEventListener('click', () => {
          appIdInput.value = preset.appId;
          installDirInput.value = preset.dir;

          // Set platform if available
          const platformSelect = document.getElementById('platform');
          if (platformSelect && preset.platform) {
            platformSelect.value = preset.platform;
          }

          // Select anonymous
          const anonRadio = document.querySelector('input[name="authMode"][value="anonymous"]');
          if (anonRadio) {
            anonRadio.checked = true;
            credentialsBox.classList.add('hidden');
          }

          lookupApp(preset.appId);
        });
        presetChips.appendChild(chip);
      });
    } catch (err) {
      presetChips.innerHTML = '<span class="text-muted">Presets unavailable</span>';
    }
  }

  // Fetch Storage
  async function fetchStorage() {
    try {
      const res = await fetch('/api/storage');
      const data = await res.json();
      if (data && data.storage && data.storage.totalFormatted !== 'Unknown') {
        const s = data.storage;
        storageText.textContent = `${s.freeFormatted} Free (${s.percentUsed}% Used)`;
      } else {
        storageText.textContent = 'Ready';
      }
    } catch (e) {
      storageText.textContent = 'Ready';
    }
  }

  // Fetch History
  async function fetchHistory() {
    try {
      const res = await fetch('/api/history');
      const history = await res.json();
      if (!history || history.length === 0) {
        historyTableBody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No download history recorded yet.</td></tr>';
        return;
      }

      historyTableBody.innerHTML = history.map(job => {
        const statusClass = job.success ? 'status-completed' : (job.status === 'cancelled' ? 'status-cancelled' : 'status-error');
        const statusLabel = job.success ? 'Success' : (job.status === 'cancelled' ? 'Cancelled' : 'Failed');
        const dateStr = job.completedAt ? new Date(job.completedAt).toLocaleString() : '-';

        return `
          <tr>
            <td><code>${job.appId}</code></td>
            <td><strong>${job.appName || '-'}</strong></td>
            <td><code>${job.installDir || '-'}</code></td>
            <td>${job.anonymous ? 'Anonymous' : 'Account'}</td>
            <td><span class="status-badge ${statusClass}">${statusLabel}</span></td>
            <td>${dateStr}</td>
          </tr>
        `;
      }).join('');
    } catch (err) {
      console.warn('History fetch failed:', err);
    }
  }

  // Clear History
  btnClearHistory.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to clear download history?')) return;
    try {
      await fetch('/api/history', { method: 'DELETE' });
      fetchHistory();
    } catch (err) {
      alert('Failed to clear history');
    }
  });

  // Start Download Form Submit
  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(form);
    const authMode = formData.get('authMode');
    const isAnonymous = authMode === 'anonymous';

    const payload = {
      appId: formData.get('appId'),
      installDir: formData.get('installDir'),
      anonymous: isAnonymous,
      username: isAnonymous ? '' : formData.get('username'),
      password: isAnonymous ? '' : formData.get('password'),
      steamGuardCode: isAnonymous ? '' : formData.get('steamGuardCode'),
      platform: formData.get('platform'),
      validate: !!formData.get('validate'),
      beta: formData.get('beta'),
      betaPassword: formData.get('betaPassword')
    };

    setDownloadingUI(true);

    try {
      const res = await fetch('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        alert(`Failed to start download: ${data.error || 'Unknown error'}`);
        setDownloadingUI(false);
      }
    } catch (err) {
      alert(`Network error starting download: ${err.message}`);
      setDownloadingUI(false);
    }
  });

  // Cancel Download
  btnCancel.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to cancel the current download?')) return;
    try {
      await fetch('/api/cancel', { method: 'POST' });
    } catch (err) {
      alert('Failed to send cancel signal.');
    }
  });

  // Modal Submit Code
  btnModalSubmit.addEventListener('click', submitSteamGuard);
  modalInput.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') submitSteamGuard();
  });

  async function submitSteamGuard() {
    const code = modalInput.value.trim();
    if (!code) {
      alert('Please enter your Steam Guard code.');
      return;
    }

    try {
      btnModalSubmit.disabled = true;
      const res = await fetch('/api/steamguard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      });
      const data = await res.json();
      if (data.success) {
        modal.classList.add('hidden');
        modalInput.value = '';
      } else {
        alert(`Error: ${data.error}`);
      }
    } catch (err) {
      alert(`Error submitting code: ${err.message}`);
    } finally {
      btnModalSubmit.disabled = false;
    }
  }

  btnModalCancel.addEventListener('click', () => {
    modal.classList.add('hidden');
    fetch('/api/cancel', { method: 'POST' });
  });

  // UI state toggles
  function setDownloadingUI(isDownloading) {
    btnSubmit.disabled = isDownloading;
    if (isDownloading) {
      btnSubmit.classList.add('hidden');
      btnCancel.classList.remove('hidden');
    } else {
      btnSubmit.classList.remove('hidden');
      btnCancel.classList.add('hidden');
    }
  }

  function updateStatusBadge(status) {
    globalBadge.className = 'status-badge';
    const s = (status || 'idle').toLowerCase();

    if (['downloading', 'validating'].includes(s)) {
      globalBadge.classList.add('status-downloading');
      globalBadgeText.textContent = s === 'validating' ? 'Validating' : 'Downloading';
      setDownloadingUI(true);
    } else if (['starting', 'logging_in'].includes(s)) {
      globalBadge.classList.add('status-starting');
      globalBadgeText.textContent = 'Connecting...';
      setDownloadingUI(true);
    } else if (s === 'paused_2fa') {
      globalBadge.classList.add('status-paused_2fa');
      globalBadgeText.textContent = 'Steam Guard 2FA';
      modal.classList.remove('hidden');
      modalInput.focus();
      setDownloadingUI(true);
    } else if (s === 'completed') {
      globalBadge.classList.add('status-completed');
      globalBadgeText.textContent = 'Completed';
      setDownloadingUI(false);
    } else if (s === 'error' || s === 'cancelled') {
      globalBadge.classList.add('status-error');
      globalBadgeText.textContent = s === 'cancelled' ? 'Cancelled' : 'Error';
      setDownloadingUI(false);
    } else {
      globalBadge.classList.add('status-idle');
      globalBadgeText.textContent = 'Idle';
      setDownloadingUI(false);
    }
  }

  // Server-Sent Events
  function initSSE() {
    if (eventSource) {
      eventSource.close();
    }

    eventSource = new EventSource('/api/stream');

    eventSource.addEventListener('status', (e) => {
      const data = JSON.parse(e.data);
      updateStatusBadge(data.status);

      if (data.job) {
        dashAppName.textContent = `${data.job.appName} (${data.job.appId})`;
        if (data.job.progress) {
          const p = data.job.progress;
          dashStage.textContent = p.stage || data.status;
          dashSpeed.textContent = p.speedFormatted || '0 B/s';
          dashSize.textContent = `${p.bytesCurrentFormatted} / ${p.bytesTotalFormatted}`;

          const pct = (p.percent || 0).toFixed(1);
          progressFill.style.width = `${pct}%`;
          progressPercent.textContent = `${pct}%`;
          progressDesc.textContent = `${p.stage} (${p.bytesCurrentFormatted} / ${p.bytesTotalFormatted})`;
        }
      } else if (data.status === 'idle') {
        dashAppName.textContent = 'None';
        dashStage.textContent = 'Idle';
        dashSpeed.textContent = '0 B/s';
        dashSize.textContent = '0 B / 0 B';
        progressFill.style.width = '0%';
        progressPercent.textContent = '0.0%';
        progressDesc.textContent = 'Ready for task';
      }
    });

    eventSource.addEventListener('log', (e) => {
      const log = JSON.parse(e.data);
      appendTerminalLog(log);
    });

    eventSource.addEventListener('steamguard', () => {
      modal.classList.remove('hidden');
      modalInput.focus();
    });

    eventSource.addEventListener('complete', () => {
      fetchHistory();
      fetchStorage();
      setDownloadingUI(false);
    });

    eventSource.onerror = () => {
      // Reconnect automatically
      setTimeout(initSSE, 4000);
    };
  }

  function appendTerminalLog(log) {
    const span = document.createElement('span');
    span.className = `log-${log.type}`;
    span.textContent = `[${log.timestamp}] ${log.text}\n`;
    terminal.appendChild(span);

    if (autoScroll) {
      terminal.scrollTop = terminal.scrollHeight;
    }
  }

  // Terminal Controls
  btnAutoscroll.addEventListener('click', () => {
    autoScroll = !autoScroll;
    btnAutoscroll.classList.toggle('active', autoScroll);
  });

  btnClearLogs.addEventListener('click', () => {
    terminal.innerHTML = '<span class="log-system">[VaporFetch] Console cleared.</span>\n';
  });

  btnCopyLogs.addEventListener('click', () => {
    navigator.clipboard.writeText(terminal.innerText).then(() => {
      const oldTitle = btnCopyLogs.title;
      btnCopyLogs.title = 'Copied!';
      setTimeout(() => btnCopyLogs.title = oldTitle, 1500);
    });
  });
});

