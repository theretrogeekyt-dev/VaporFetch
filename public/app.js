document.addEventListener('DOMContentLoaded', () => {
  // Navigation & Tabs
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');
  const libraryCountBadge = document.getElementById('library-count-badge');
  const activeBanner = document.getElementById('active-task-banner');
  const bannerGameName = document.getElementById('banner-game-name');
  const bannerSpeed = document.getElementById('banner-speed');
  const bannerProgressFill = document.getElementById('banner-progress-fill');
  const bannerPercent = document.getElementById('banner-percent');
  const btnBannerView = document.getElementById('btn-banner-view');

  // Library Elements
  const libraryGrid = document.getElementById('library-grid');
  const librarySearch = document.getElementById('library-search');
  const filterChips = document.querySelectorAll('.filter-chip');
  const btnOpenSyncModal = document.getElementById('btn-open-sync-modal');
  const btnOpenAddGame = document.getElementById('btn-open-add-game');

  // Direct Form Elements
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
  const btnCancelActive = document.getElementById('btn-cancel-active');
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

  // Modals
  const syncModal = document.getElementById('sync-modal');
  const syncIdentifier = document.getElementById('sync-identifier');
  const syncApiKey = document.getElementById('sync-apikey');
  const btnSubmitSync = document.getElementById('btn-submit-sync');

  const addGameModal = document.getElementById('add-game-modal');
  const addAppId = document.getElementById('add-appid');
  const addName = document.getElementById('add-name');
  const addType = document.getElementById('add-type');
  const btnSubmitAddGame = document.getElementById('btn-submit-add-game');

  const quickModal = document.getElementById('quick-download-modal');
  const quickForm = document.getElementById('quick-download-form');
  const quickModalImg = document.getElementById('quick-modal-img');
  const quickModalName = document.getElementById('quick-modal-name');
  const quickModalAppId = document.getElementById('quick-modal-appid');
  const quickAppIdInput = document.getElementById('quick-appid');
  const quickDirInput = document.getElementById('quick-dir');
  const quickCredsBox = document.getElementById('quick-creds-box');
  const quickAuthRadios = document.querySelectorAll('input[name="quickAuthMode"]');

  const guardModal = document.getElementById('steamguard-modal');
  const guardModalInput = document.getElementById('modal-guard-code');
  const btnModalSubmit = document.getElementById('modal-submit-code');
  const btnModalCancel = document.getElementById('modal-cancel-download');

  // App State
  let autoScroll = true;
  let eventSource = null;
  let allGames = [];
  let currentFilter = 'all';
  let searchQuery = '';

  // Initialize Application
  initTabs();
  initModals();
  initSSE();
  fetchStorage();
  fetchLibrary();
  fetchPresets();
  fetchHistory();

  // Tab Navigation Handling
  function initTabs() {
    tabButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const targetTab = btn.getAttribute('data-tab');
        switchTab(targetTab);
      });
    });

    btnBannerView.addEventListener('click', () => {
      switchTab('tab-monitor');
    });
  }

  function switchTab(tabId) {
    tabButtons.forEach(b => {
      if (b.getAttribute('data-tab') === tabId) {
        b.classList.add('active');
      } else {
        b.classList.remove('active');
      }
    });

    tabContents.forEach(tc => {
      if (tc.id === tabId) {
        tc.classList.add('active');
      } else {
        tc.classList.remove('active');
      }
    });
  }

  // Modal Setup
  function initModals() {
    document.querySelectorAll('.modal-close-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.modal-backdrop').forEach(m => m.classList.add('hidden'));
      });
    });

    const closeSyncBtn = document.getElementById('btn-close-sync-modal');
    if (closeSyncBtn) {
      closeSyncBtn.addEventListener('click', () => syncModal.classList.add('hidden'));
    }

    btnOpenSyncModal.addEventListener('click', () => {
      syncModal.classList.remove('hidden');
      syncIdentifier.focus();
    });

    btnOpenAddGame.addEventListener('click', () => {
      addGameModal.classList.remove('hidden');
      addAppId.focus();
    });

    // Quick Auth Radio Toggle
    quickAuthRadios.forEach(r => {
      r.addEventListener('change', () => {
        if (r.value === 'account') {
          quickCredsBox.classList.remove('hidden');
        } else {
          quickCredsBox.classList.add('hidden');
        }
      });
    });
  }

  // Fetch and Render Games Library
  async function fetchLibrary() {
    try {
      const res = await fetch('/api/library');
      allGames = await res.json();
      libraryCountBadge.textContent = allGames.length;
      renderLibrary();
    } catch (err) {
      libraryGrid.innerHTML = '<div class="library-empty text-muted">Failed to load library.</div>';
    }
  }

  function renderLibrary() {
    let filtered = allGames.filter(game => {
      // Search text match
      const matchSearch = !searchQuery || 
        game.name.toLowerCase().includes(searchQuery) || 
        game.appId.includes(searchQuery);

      // Category filter match
      let matchCat = true;
      if (currentFilter === 'owned') matchCat = game.isUserOwned || game.type === 'game';
      else if (currentFilter === 'servers') matchCat = game.type === 'server' || game.anonymous;
      else if (currentFilter === 'installed') matchCat = !!game.isInstalled;

      return matchSearch && matchCat;
    });

    if (filtered.length === 0) {
      libraryGrid.innerHTML = `
        <div class="library-empty text-muted">
          <p>No games found matching your filter.</p>
          <button type="button" class="btn-secondary btn-sm" id="btn-empty-sync" style="margin-top: 1rem;">Sync Steam Account</button>
        </div>
      `;
      const btnEmptySync = document.getElementById('btn-empty-sync');
      if (btnEmptySync) {
        btnEmptySync.addEventListener('click', () => syncModal.classList.remove('hidden'));
      }
      return;
    }

    libraryGrid.innerHTML = filtered.map(game => {
      const isServer = game.type === 'server' || game.anonymous;
      const typeBadge = isServer ? 'Server' : (game.isUserOwned ? 'Owned' : 'Game');
      const installedBadge = game.isInstalled ? '<span class="game-card-badge badge-installed">NAS Installed</span>' : '';

      return `
        <div class="game-card" data-appid="${game.appId}">
          <div class="game-card-img-wrap">
            <img src="${game.headerImage}" alt="${game.name}" class="game-card-img" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 460 215%22 fill=%22%23101620%22><text x=%2250%%22 y=%2250%%22 fill=%22%2364748b%22 text-anchor=%22middle%22 dominant-baseline=%22middle%22 font-family=%22sans-serif%22 font-size=%2224%22>${game.appId}</text></svg>'">
            <span class="game-card-badge">${typeBadge}</span>
            ${installedBadge}
          </div>
          <div class="game-card-body">
            <h4 class="game-card-title" title="${game.name}">${game.name}</h4>
            <div class="game-card-meta">
              <span>AppID: ${game.appId}</span>
              <span>${game.platform === 'windows' ? 'Windows' : 'Linux'}</span>
            </div>
            <button type="button" class="btn-primary btn-sm game-card-btn" data-appid="${game.appId}">
              <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
              <span>Download to NAS</span>
            </button>
          </div>
        </div>
      `;
    }).join('');

    // Attach click listeners to cards
    libraryGrid.querySelectorAll('.game-card-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = btn.getAttribute('data-appid');
        openQuickDownloadModal(id);
      });
    });
  }

  // Search & Filter Listeners
  librarySearch.addEventListener('input', (e) => {
    searchQuery = e.target.value.toLowerCase().trim();
    renderLibrary();
  });

  filterChips.forEach(chip => {
    chip.addEventListener('click', () => {
      filterChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      currentFilter = chip.getAttribute('data-filter');
      renderLibrary();
    });
  });

  // Open Quick Download Modal
  function openQuickDownloadModal(appId) {
    const game = allGames.find(g => g.appId === appId);
    if (!game) return;

    quickAppIdInput.value = game.appId;
    quickModalName.textContent = game.name;
    quickModalAppId.textContent = `AppID: ${game.appId}`;
    quickModalImg.src = game.headerImage;
    quickDirInput.value = game.targetFolder || game.dir || game.appId;

    const isAnonymous = game.anonymous || game.type === 'server';
    const authRadio = document.querySelector(`input[name="quickAuthMode"][value="${isAnonymous ? 'anonymous' : 'account'}"]`);
    if (authRadio) {
      authRadio.checked = true;
      if (isAnonymous) {
        quickCredsBox.classList.add('hidden');
      } else {
        quickCredsBox.classList.remove('hidden');
      }
    }

    const platformSelect = document.getElementById('quick-platform');
    if (platformSelect && game.platform) {
      platformSelect.value = game.platform;
    }

    quickModal.classList.remove('hidden');
  }

  // Quick Download Form Submit
  quickForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(quickForm);
    const authMode = formData.get('quickAuthMode');
    const isAnonymous = authMode === 'anonymous';

    const payload = {
      appId: formData.get('appId'),
      installDir: formData.get('installDir'),
      anonymous: isAnonymous,
      username: isAnonymous ? '' : formData.get('username'),
      password: isAnonymous ? '' : formData.get('password'),
      platform: formData.get('platform'),
      validate: !!formData.get('validate'),
      removeSteamApps: true,
      renameRedist: true
    };

    quickModal.classList.add('hidden');
    setDownloadingUI(true);
    switchTab('tab-monitor');

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
      alert(`Network error: ${err.message}`);
      setDownloadingUI(false);
    }
  });

  // Sync Steam Account Submit
  btnSubmitSync.addEventListener('click', async () => {
    const identifier = syncIdentifier.value.trim();
    if (!identifier) {
      alert('Please enter your Steam username, vanity URL, or SteamID64.');
      return;
    }

    btnSubmitSync.disabled = true;
    btnSubmitSync.textContent = 'Syncing...';

    try {
      const res = await fetch('/api/library/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          identifier,
          apiKey: syncApiKey.value.trim()
        })
      });
      const data = await res.json();

      if (data.success) {
        syncModal.classList.add('hidden');
        alert(`Sync complete! Found ${data.totalImported} games (${data.newlyAdded} newly added).`);
        fetchLibrary();
      } else {
        alert(`Sync error: ${data.error}`);
      }
    } catch (err) {
      alert(`Sync failed: ${err.message}`);
    } finally {
      btnSubmitSync.disabled = false;
      btnSubmitSync.textContent = 'Sync Games';
    }
  });

  // Add Custom Game Submit
  btnSubmitAddGame.addEventListener('click', async () => {
    const id = addAppId.value.trim();
    if (!id) {
      alert('AppID is required.');
      return;
    }

    try {
      btnSubmitAddGame.disabled = true;
      const res = await fetch('/api/library', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          appId: id,
          name: addName.value.trim() || `App ${id}`,
          type: addType.value
        })
      });
      const data = await res.json();
      if (data.success) {
        addGameModal.classList.add('hidden');
        addAppId.value = '';
        addName.value = '';
        fetchLibrary();
      } else {
        alert(`Error: ${data.error}`);
      }
    } catch (err) {
      alert(`Failed to add game: ${err.message}`);
    } finally {
      btnSubmitAddGame.disabled = false;
    }
  });

  // Direct Download Form Submit
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
      removeSteamApps: !!formData.get('removeSteamApps'),
      renameRedist: !!formData.get('renameRedist'),
      beta: formData.get('beta'),
      betaPassword: formData.get('betaPassword')
    };

    setDownloadingUI(true);
    switchTab('tab-monitor');

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

  // Cancel Download (From direct form or active monitor)
  [btnCancel, btnCancelActive].forEach(btn => {
    if (btn) {
      btn.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to cancel the active download?')) return;
        try {
          await fetch('/api/cancel', { method: 'POST' });
        } catch (err) {
          alert('Failed to send cancel signal.');
        }
      });
    }
  });

  // Direct Auth Radio Toggle
  authRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      if (radio.value === 'account') {
        credentialsBox.classList.remove('hidden');
      } else {
        credentialsBox.classList.add('hidden');
      }
    });
  });

  // AppID Inspect Lookup
  btnLookup.addEventListener('click', () => lookupApp(appIdInput.value));
  appIdInput.addEventListener('change', () => {
    if (appIdInput.value.trim()) lookupApp(appIdInput.value);
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

  // Steam Guard 2FA Submission
  btnModalSubmit.addEventListener('click', submitSteamGuard);
  guardModalInput.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') submitSteamGuard();
  });

  async function submitSteamGuard() {
    const code = guardModalInput.value.trim();
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
        guardModal.classList.add('hidden');
        guardModalInput.value = '';
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
    guardModal.classList.add('hidden');
    fetch('/api/cancel', { method: 'POST' });
  });

  // UI State Updater
  function setDownloadingUI(isDownloading) {
    btnSubmit.disabled = isDownloading;
    if (isDownloading) {
      btnSubmit.classList.add('hidden');
      btnCancel.classList.remove('hidden');
      btnCancelActive.classList.remove('hidden');
      activeBanner.classList.remove('hidden');
    } else {
      btnSubmit.classList.remove('hidden');
      btnCancel.classList.add('hidden');
      btnCancelActive.classList.add('hidden');
      activeBanner.classList.add('hidden');
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
      guardModal.classList.remove('hidden');
      guardModalInput.focus();
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

  // Real-time Server-Sent Events (SSE) Listener
  function initSSE() {
    if (eventSource) {
      eventSource.close();
    }

    eventSource = new EventSource('/api/stream');

    eventSource.addEventListener('status', (e) => {
      const data = JSON.parse(e.data);
      updateStatusBadge(data.status);

      if (data.job) {
        const j = data.job;
        dashAppName.textContent = `${j.appName} (${j.appId})`;
        bannerGameName.textContent = j.appName;

        if (j.progress) {
          const p = j.progress;
          const pct = (p.percent || 0).toFixed(1);
          const speed = p.speedFormatted || '0 B/s';
          const sizeStr = `${p.bytesCurrentFormatted} / ${p.bytesTotalFormatted}`;

          // Update main monitor dashboard
          dashStage.textContent = p.stage || data.status;
          dashSpeed.textContent = speed;
          dashSize.textContent = sizeStr;
          progressFill.style.width = `${pct}%`;
          progressPercent.textContent = `${pct}%`;
          progressDesc.textContent = `${p.stage} (${sizeStr})`;

          // Update top active banner
          bannerSpeed.textContent = speed;
          bannerProgressFill.style.width = `${pct}%`;
          bannerPercent.textContent = `${pct}%`;
        }
      } else if (data.status === 'idle') {
        dashAppName.textContent = 'None';
        dashStage.textContent = 'Idle';
        dashSpeed.textContent = '0 B/s';
        dashSize.textContent = '0 B / 0 B';
        progressFill.style.width = '0%';
        progressPercent.textContent = '0.0%';
        progressDesc.textContent = 'Ready for task';
        activeBanner.classList.add('hidden');
      }
    });

    eventSource.addEventListener('log', (e) => {
      const log = JSON.parse(e.data);
      appendTerminalLog(log);
    });

    eventSource.addEventListener('steamguard', () => {
      guardModal.classList.remove('hidden');
      guardModalInput.focus();
    });

    eventSource.addEventListener('complete', () => {
      fetchHistory();
      fetchStorage();
      fetchLibrary();
      setDownloadingUI(false);
    });

    eventSource.onerror = () => {
      setTimeout(initSSE, 4000);
    };
  }

  // Replicate Terminal In-Place Carriage Return Updating
  function appendTerminalLog(log) {
    const lastChild = terminal.lastElementChild;

    // If this is an in-place progress update and the last line was also a progress update, overwrite it!
    if (log.isProgress && lastChild && lastChild.classList.contains('log-progress')) {
      lastChild.textContent = `[${log.timestamp}] ${log.text}\n`;
    } else {
      const span = document.createElement('span');
      span.className = `log-${log.type}${log.isProgress ? ' log-progress' : ''}`;
      span.textContent = `[${log.timestamp}] ${log.text}\n`;
      terminal.appendChild(span);
    }

    if (autoScroll) {
      terminal.scrollTop = terminal.scrollHeight;
    }
  }

  // Console Tools
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

  // Storage and Presets
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
          const platformSelect = document.getElementById('platform');
          if (platformSelect && preset.platform) platformSelect.value = preset.platform;
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

  btnClearHistory.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to clear download history?')) return;
    try {
      await fetch('/api/history', { method: 'DELETE' });
      fetchHistory();
    } catch (err) {
      alert('Failed to clear history');
    }
  });
});
