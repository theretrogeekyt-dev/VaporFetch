// VaporFetch Mobile - Android Optimized Client Logic

let currentUser = null;
let allGames = [];
let filteredGames = [];
let selectedGames = new Map(); // appid -> {appid, name}
let activeDownloadItem = null;
let sseConnection = null;
let qrPollTimer = null;
let steamCmdAuthPollTimer = null;
let autoScrollLogs = true;
let currentUpdateInfo = null;

// Initialization
document.addEventListener("DOMContentLoaded", () => {
  checkAuthSession();
  fetchSystemStatus();
  initSSE();
  checkForUpdates();
  loadSettings();
  setInterval(fetchSystemStatus, 30000);
});

// Haptic feedback helper for native Android touch feel
function vibrate(ms = 12) {
  try {
    if (navigator.vibrate) {
      navigator.vibrate(ms);
    }
  } catch (e) {}
}

// ---------------- Toast Notifications ---------------- //
function showToast(message, isError = false) {
  const container = document.getElementById("mobileToastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `mobile-toast ${isError ? 'toast-error' : ''}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 250);
  }, 3200);
}

// ---------------- Navigation & Tab Switching ---------------- //
function switchMobileTab(tabId) {
  vibrate(10);
  const views = document.querySelectorAll(".mobile-tab-view");
  const navTabs = document.querySelectorAll(".nav-tab");

  views.forEach(v => v.classList.remove("active"));
  navTabs.forEach(t => t.classList.remove("active"));

  const targetView = document.getElementById(tabId);
  if (targetView) targetView.classList.add("active");

  const tabIndexMap = {
    'tabLibrary': 0,
    'tabQueue': 1,
    'tabConsole': 2,
    'tabSettings': 3
  };

  const idx = tabIndexMap[tabId];
  if (idx !== undefined && navTabs[idx]) {
    navTabs[idx].classList.add("active");
  }

  if (tabId === "tabQueue") {
    fetchQueue();
  } else if (tabId === "tabSettings") {
    loadSettings();
    updateSettingsAuthStatus();
  }
}

function switchToConsoleTab() {
  switchMobileTab("tabConsole");
}

// ---------------- Storage & System Status ---------------- //
async function fetchSystemStatus() {
  try {
    const res = await fetch("/api/system/status");
    if (!res.ok) return;
    const data = await res.json();

    const disk = data.disk || {};
    const freeBytes = disk.free_bytes || 0;
    const totalBytes = disk.total_bytes || 0;
    const freeGB = freeBytes / (1024 ** 3);
    const totalGB = totalBytes / (1024 ** 3);

    const storageText = document.getElementById("mobileStorageText");
    const storageChip = document.getElementById("mobileStorageChip");
    if (storageText) {
      if (freeGB >= 1000) {
        storageText.textContent = `${(freeGB / 1024).toFixed(1)} TB free`;
      } else {
        storageText.textContent = `${freeGB.toFixed(1)} GB free`;
      }
    }
    if (storageChip) {
      storageChip.title = `NAS Storage: ${freeGB.toFixed(1)} GB free of ${totalGB.toFixed(1)} GB total`;
    }

    const puidEl = document.getElementById("mSysPuidPgid");
    if (puidEl) puidEl.textContent = `${data.puid || '1000'} / ${data.pgid || '1000'}`;
    const downDirEl = document.getElementById("mSysDownDir");
    if (downDirEl) downDirEl.textContent = data.download_dir || '/downloads';
    const dataDirEl = document.getElementById("mSysDataDir");
    if (dataDirEl) dataDirEl.textContent = data.data_dir || '/app/data';
  } catch (e) {
    console.warn("Could not fetch system status:", e);
  }
}

// ---------------- Authentication (Steam Guard QR) ---------------- //
async function checkAuthSession() {
  try {
    const res = await fetch("/api/auth/session");
    const data = await res.json();

    if (data.authenticated && data.session) {
      currentUser = data.session;
      renderAuthenticatedUser(currentUser);
      loadLibrary();
    } else {
      currentUser = null;
      renderUnauthenticatedUser();
    }
  } catch (e) {
    renderUnauthenticatedUser();
  }
}

function renderAuthenticatedUser(session) {
  const loginBtn = document.getElementById("mobileLoginBtn");
  const userCard = document.getElementById("mobileUserCard");
  const userAvatar = document.getElementById("mobileUserAvatar");
  const userName = document.getElementById("mobileUserName");
  const authPrompt = document.getElementById("mobileAuthPrompt");
  const libraryToolbar = document.getElementById("mobileLibraryToolbar");

  if (loginBtn) loginBtn.style.display = "none";
  if (userCard) userCard.style.display = "flex";
  if (userAvatar) {
    userAvatar.src = session.avatar || "data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 24 24%22 fill=%22%2338bdf8%22><circle cx=%2212%22 cy=%2212%22 r=%2210%22/></svg>";
  }
  if (userName) {
    userName.textContent = session.personaname || session.account_name || "Steam User";
  }

  if (authPrompt) authPrompt.style.display = "none";
  if (libraryToolbar) libraryToolbar.style.display = "block";
}

function renderUnauthenticatedUser() {
  const loginBtn = document.getElementById("mobileLoginBtn");
  const userCard = document.getElementById("mobileUserCard");
  const authPrompt = document.getElementById("mobileAuthPrompt");
  const libraryToolbar = document.getElementById("mobileLibraryToolbar");
  const gamesGrid = document.getElementById("mobileGamesGrid");
  const loading = document.getElementById("mobileLibraryLoading");
  const empty = document.getElementById("mobileLibraryEmpty");

  if (loginBtn) loginBtn.style.display = "inline-flex";
  if (userCard) userCard.style.display = "none";
  if (authPrompt) authPrompt.style.display = "block";
  if (libraryToolbar) libraryToolbar.style.display = "none";
  if (gamesGrid) gamesGrid.innerHTML = "";
  if (loading) loading.style.display = "none";
  if (empty) empty.style.display = "none";
}

function handleUserChipClick() {
  vibrate(10);
  if (currentUser) {
    // Open profile bottom sheet
    openProfileModal();
  } else {
    // Open Steam Guard login modal
    openLoginModal();
  }
}

function openProfileModal() {
  const modal = document.getElementById("mobileProfileModal");
  if (!modal || !currentUser) return;

  const avatar = document.getElementById("mProfileAvatar");
  const name = document.getElementById("mProfileName");
  const id = document.getElementById("mProfileId");

  if (avatar) avatar.src = currentUser.avatar || "";
  if (name) name.textContent = currentUser.personaname || currentUser.account_name || "Steam User";
  if (id) id.textContent = `SteamID: ${currentUser.steamid || '--'}`;

  modal.style.display = "flex";
}

function closeProfileModal() {
  const modal = document.getElementById("mobileProfileModal");
  if (modal) modal.style.display = "none";
}

async function logoutMobile() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
    closeProfileModal();
    currentUser = null;
    allGames = [];
    filteredGames = [];
    selectedGames.clear();
    updateBatchSheet();
    renderUnauthenticatedUser();
    showToast("Logged out of Steam.");
  } catch (e) {
    showToast("Logout failed: " + e.message, true);
  }
}

// ---------------- Steam Guard Mobile Login (App Approval) ---------------- //
let mobileLoginPollTimer = null;

function openLoginModal() {
  vibrate(12);
  const modal = document.getElementById("mobileLoginModal");
  if (!modal) return;

  const formStage = document.getElementById("mLoginFormStage");
  const approvalStage = document.getElementById("mLoginApprovalStage");
  const successStage = document.getElementById("mLoginSuccessStage");
  const errEl = document.getElementById("mLoginError");
  const usernameInput = document.getElementById("mLoginUsername");
  const passInput = document.getElementById("mLoginPassword");

  if (formStage) formStage.style.display = "block";
  if (approvalStage) approvalStage.style.display = "none";
  if (successStage) successStage.style.display = "none";
  if (errEl) errEl.style.display = "none";

  // Pre-fill username from settings if available
  const settingsUser = document.getElementById("mCfgUsername")?.value || "";
  if (usernameInput && !usernameInput.value && settingsUser) {
    usernameInput.value = settingsUser;
  }
  if (passInput) passInput.value = "";

  modal.style.display = "flex";
}

function closeLoginModal() {
  if (mobileLoginPollTimer) {
    clearInterval(mobileLoginPollTimer);
    mobileLoginPollTimer = null;
  }
  const modal = document.getElementById("mobileLoginModal");
  if (modal) modal.style.display = "none";
}

function toggleMobileApiKey(event) {
  if (event) event.preventDefault();
  const wrap = document.getElementById("mLoginApiKeyWrap");
  if (wrap) {
    wrap.style.display = wrap.style.display === "none" ? "block" : "none";
  }
}

async function submitMobileLogin(event) {
  event.preventDefault();
  const username = document.getElementById("mLoginUsername")?.value?.trim() || "";
  const password = document.getElementById("mLoginPassword")?.value || "";
  const apiKey = document.getElementById("mLoginApiKey")?.value?.trim() || "";
  const errEl = document.getElementById("mLoginError");

  if (!username || !password) {
    if (errEl) {
      errEl.textContent = "Please enter both username and password.";
      errEl.style.display = "block";
    }
    return;
  }

  if (errEl) errEl.style.display = "none";

  const formStage = document.getElementById("mLoginFormStage");
  const approvalStage = document.getElementById("mLoginApprovalStage");
  const statusText = document.getElementById("mLoginStatusText");

  if (formStage) formStage.style.display = "none";
  if (approvalStage) approvalStage.style.display = "block";
  if (statusText) statusText.textContent = "Connecting to Steam servers...";

  try {
    const res = await fetch("/api/auth/steamcmd/authorize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: username,
        password: password,
        api_key: apiKey || undefined
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to initiate Steam login");
    }

    pollMobileLoginStatus();
  } catch (e) {
    if (formStage) formStage.style.display = "block";
    if (approvalStage) approvalStage.style.display = "none";
    if (errEl) {
      errEl.textContent = e.message;
      errEl.style.display = "block";
    }
    showToast(e.message, true);
  }
}

function pollMobileLoginStatus() {
  if (mobileLoginPollTimer) clearInterval(mobileLoginPollTimer);

  mobileLoginPollTimer = setInterval(async () => {
    try {
      const res = await fetch("/api/auth/steamcmd/status");
      if (!res.ok) return;
      const data = await res.json();

      const statusText = document.getElementById("mLoginStatusText");
      const fallbackWrap = document.getElementById("mLoginFallbackWrap");

      if (data.state === "waiting_approval") {
        if (statusText) statusText.textContent = "Steam Guard request sent! Please tap 'Approve' in your Steam Mobile app.";
      } else if (data.state === "waiting_code") {
        if (statusText) statusText.textContent = "Steam Guard code required. Enter your 5-character code below:";
        if (fallbackWrap) fallbackWrap.style.display = "block";
        document.getElementById("mLoginCodeInput")?.focus();
      } else if (data.status_message) {
        if (statusText) statusText.textContent = data.status_message;
      }

      // Check success
      if (data.authorized || data.state === "success") {
        clearInterval(mobileLoginPollTimer);
        mobileLoginPollTimer = null;
        vibrate([20, 60, 20]);

        const approvalStage = document.getElementById("mLoginApprovalStage");
        const successStage = document.getElementById("mLoginSuccessStage");
        const successUser = document.getElementById("mLoginSuccessUser");

        if (approvalStage) approvalStage.style.display = "none";
        if (successStage) successStage.style.display = "block";
        if (successUser) {
          successUser.textContent = `Connected as ${data.username || "Steam User"}`;
        }

        showToast("Logged in to Steam successfully! ✅");

        // Reload session and library
        await checkAuthSession();

        setTimeout(() => {
          closeLoginModal();
        }, 1500);
      } else if (data.state === "error") {
        clearInterval(mobileLoginPollTimer);
        mobileLoginPollTimer = null;
        vibrate(40);

        const formStage = document.getElementById("mLoginFormStage");
        const approvalStage = document.getElementById("mLoginApprovalStage");
        const errEl = document.getElementById("mLoginError");

        if (formStage) formStage.style.display = "block";
        if (approvalStage) approvalStage.style.display = "none";
        if (errEl) {
          errEl.textContent = data.status_message || "Login failed. Please verify credentials.";
          errEl.style.display = "block";
        }
        showToast(data.status_message || "Steam login failed", true);
      }
    } catch (e) {
      console.warn("Poll login error:", e);
    }
  }, 2000);
}

async function submitMobileLoginCode() {
  const codeInput = document.getElementById("mLoginCodeInput");
  const code = codeInput?.value?.trim() || "";
  if (!code) return;

  try {
    const res = await fetch("/api/auth/steamcmd/code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: code })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to submit code");
    }
    showToast("Submitted Steam Guard code, verifying...");
  } catch (e) {
    showToast(e.message, true);
  }
}

async function cancelMobileLogin() {
  try {
    await fetch("/api/auth/steamcmd/cancel", { method: "POST" });
  } catch (e) {}

  if (mobileLoginPollTimer) {
    clearInterval(mobileLoginPollTimer);
    mobileLoginPollTimer = null;
  }

  const formStage = document.getElementById("mLoginFormStage");
  const approvalStage = document.getElementById("mLoginApprovalStage");
  if (formStage) formStage.style.display = "block";
  if (approvalStage) approvalStage.style.display = "none";
}

function openDeviceAuthFromSettings() {
  openLoginModal();
}

// ---------------- Game Library ---------------- //
async function loadLibrary() {
  const loading = document.getElementById("mobileLibraryLoading");
  const empty = document.getElementById("mobileLibraryEmpty");
  const grid = document.getElementById("mobileGamesGrid");

  if (loading) loading.style.display = "block";
  if (empty) empty.style.display = "none";
  if (grid) grid.innerHTML = "";

  try {
    const res = await fetch("/api/games");
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to load library");
    }
    const data = await res.json();
    allGames = data.games || [];
    filteredGames = [...allGames];

    if (loading) loading.style.display = "none";
    if (allGames.length === 0) {
      if (empty) empty.style.display = "block";
    } else {
      renderMobileGames();
    }
  } catch (e) {
    if (loading) loading.style.display = "none";
    if (empty) {
      empty.style.display = "block";
      const msg = document.getElementById("mobileLibraryEmptyMsg");
      if (msg) msg.textContent = e.message;
    }
    showToast(e.message, true);
  }
}

function renderMobileGames() {
  const grid = document.getElementById("mobileGamesGrid");
  const empty = document.getElementById("mobileLibraryEmpty");
  if (!grid) return;

  if (filteredGames.length === 0) {
    grid.innerHTML = "";
    if (empty) {
      empty.style.display = "block";
      const msg = document.getElementById("mobileLibraryEmptyMsg");
      if (msg) msg.textContent = "No matching games found.";
    }
    return;
  }

  if (empty) empty.style.display = "none";

  grid.innerHTML = filteredGames.map(game => {
    const isSelected = selectedGames.has(game.appid);
    const banner = game.header_url || "data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 460 215%22 fill=%22%23162036%22></svg>";
    const hours = Math.round((game.playtime_forever || 0) / 60);

    return `
      <div class="mobile-game-card ${isSelected ? 'selected' : ''}" onclick="toggleGameSelectionMobile(${game.appid})">
        <div class="card-img-wrap">
          <img src="${banner}" alt="${escapeHtml(game.name)}" loading="lazy" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 460 215%22 fill=%22%23162036%22><text x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 fill=%22%2364748b%22 font-family=%22sans-serif%22 font-size=%2216%22>Steam Game</text></svg>'">
          <div class="card-checkbox-badge">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
        </div>
        <div class="card-info">
          <div class="card-title">${escapeHtml(game.name)}</div>
          <div class="card-playtime">${hours > 0 ? hours + ' hrs played' : 'Unplayed'}</div>
        </div>
      </div>
    `;
  }).join("");
}

function toggleGameSelectionMobile(appid) {
  vibrate(12);
  const game = allGames.find(g => g.appid === appid);
  if (!game) return;

  if (selectedGames.has(appid)) {
    selectedGames.delete(appid);
  } else {
    selectedGames.set(appid, { appid: game.appid, name: game.name });
  }

  updateBatchSheet();
  renderMobileGames();
}

function selectAllFilteredGames() {
  vibrate(15);
  filteredGames.forEach(g => {
    selectedGames.set(g.appid, { appid: g.appid, name: g.name });
  });
  updateBatchSheet();
  renderMobileGames();
}

function deselectAllGames() {
  vibrate(10);
  selectedGames.clear();
  updateBatchSheet();
  renderMobileGames();
}

function updateBatchSheet() {
  const sheet = document.getElementById("mobileBatchSheet");
  const countEl = document.getElementById("mBatchCount");
  const count = selectedGames.size;

  if (countEl) countEl.textContent = count;
  if (sheet) {
    sheet.style.display = count > 0 ? "flex" : "none";
  }
}

function onSearchInput(event) {
  const query = event.target.value.toLowerCase().trim();
  const clearBtn = document.getElementById("mobileSearchClear");
  if (clearBtn) clearBtn.style.display = query ? "block" : "none";

  if (!query) {
    filteredGames = [...allGames];
  } else {
    filteredGames = allGames.filter(g => (g.name || "").toLowerCase().includes(query));
  }
  renderMobileGames();
}

function clearSearch() {
  const input = document.getElementById("mobileSearchInput");
  const clearBtn = document.getElementById("mobileSearchClear");
  if (input) input.value = "";
  if (clearBtn) clearBtn.style.display = "none";
  filteredGames = [...allGames];
  renderMobileGames();
}

function refreshLibrary() {
  vibrate(15);
  loadLibrary();
}

// ---------------- Batch Download Queueing ---------------- //
async function queueSelectedGamesMobile() {
  if (selectedGames.size === 0) return;
  vibrate(20);

  const autoGoldberg = document.getElementById("mBatchGoldberg")?.checked || false;
  const gamesToQueue = Array.from(selectedGames.values());

  try {
    const res = await fetch("/api/queue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ games: gamesToQueue, require_goldberg: autoGoldberg })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to add games to queue");
    }

    const data = await res.json();
    showToast(`Added ${data.added_count} game(s) to download queue!`);
    deselectAllGames();
    switchMobileTab("tabQueue");
  } catch (e) {
    showToast(e.message, true);
  }
}

// ---------------- Download Queue View & Telemetry ---------------- //
async function fetchQueue() {
  try {
    const res = await fetch("/api/queue");
    if (!res.ok) return;
    const data = await res.json();
    renderQueueState(data);
  } catch (e) {
    console.warn("Queue fetch error:", e);
  }
}

function renderQueueState(data) {
  const items = data.items || [];
  const activeId = data.active_id;

  const runningItem = items.find(i => i.id === activeId && i.status === "running");
  const pendingItems = items.filter(i => i.status === "queued");
  const historyItems = items.filter(i => i.status === "completed" || i.status === "failed" || i.status === "cancelled");

  // Update nav badge for queue
  const navBadge = document.getElementById("mobileQueueNavBadge");
  if (navBadge) {
    const totalActive = (runningItem ? 1 : 0) + pendingItems.length;
    if (totalActive > 0) {
      navBadge.textContent = totalActive;
      navBadge.style.display = "flex";
    } else {
      navBadge.style.display = "none";
    }
  }

  // Active Download Card
  renderActiveCard(runningItem);

  // Pending List
  renderPendingQueue(pendingItems);

  // History List
  renderHistoryQueue(historyItems);
}

function renderActiveCard(item) {
  activeDownloadItem = item;
  const titleEl = document.getElementById("mobileActiveTitle");
  const appIdEl = document.getElementById("mobileActiveAppId");
  const fillEl = document.getElementById("mobileActiveFill");
  const pctEl = document.getElementById("mobileActivePct");
  const stepEl = document.getElementById("mobileActiveStep");
  const speedEl = document.getElementById("mobileActiveSpeed");
  const etaEl = document.getElementById("mobileActiveEta");
  const bytesEl = document.getElementById("mobileActiveBytes");
  const cancelBtn = document.getElementById("mobileCancelBtn");

  if (!item) {
    if (titleEl) titleEl.textContent = "No Active Download";
    if (appIdEl) appIdEl.textContent = "AppID: --";
    if (fillEl) fillEl.style.width = "0%";
    if (pctEl) pctEl.textContent = "0.0%";
    if (stepEl) stepEl.textContent = "Queue Idle";
    if (speedEl) speedEl.textContent = "0.0 MB/s";
    if (etaEl) etaEl.textContent = "--";
    if (bytesEl) bytesEl.textContent = "0 MB / 0 MB";
    if (cancelBtn) cancelBtn.style.display = "none";
    return;
  }

  if (titleEl) titleEl.textContent = item.name;
  if (appIdEl) appIdEl.textContent = `AppID: ${item.appid}`;
  if (fillEl) fillEl.style.width = `${item.progress.toFixed(1)}%`;
  if (pctEl) pctEl.textContent = `${item.progress.toFixed(1)}%`;
  if (stepEl) stepEl.textContent = item.step;

  const curMB = (item.current_bytes / (1024 ** 2)).toFixed(1);
  const totMB = (item.total_bytes / (1024 ** 2)).toFixed(1);
  if (bytesEl) bytesEl.textContent = `${curMB} MB / ${totMB} MB`;

  const speedMBs = (item.speed_bps / (1024 ** 2)).toFixed(2);
  if (speedEl) speedEl.textContent = `${speedMBs} MB/s`;

  if (etaEl) etaEl.textContent = formatEta(item.eta_seconds);
  if (cancelBtn) cancelBtn.style.display = "inline-flex";
}

function formatEta(sec) {
  if (!sec || sec <= 0) return "--";
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const r = sec % 60;
  if (m < 60) return `${m}m ${r}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function renderPendingQueue(items) {
  const container = document.getElementById("mobilePendingList");
  const countEl = document.getElementById("mobilePendingCount");
  if (countEl) countEl.textContent = items.length;
  if (!container) return;

  if (items.length === 0) {
    container.innerHTML = `<p class="empty-hint">No downloads pending.</p>`;
    return;
  }

  container.innerHTML = items.map((item, idx) => `
    <div class="queue-row">
      <div class="queue-row-info">
        <span class="queue-row-order">#${idx + 1}</span>
        <div class="queue-row-text">
          <div class="queue-row-title">${escapeHtml(item.name)}</div>
          <div class="queue-row-sub">AppID ${item.appid} &bull; ${item.step}</div>
        </div>
      </div>
      <button class="btn btn-xs btn-outline" onclick="removeQueueItem('${item.id}')">Remove</button>
    </div>
  `).join("");
}

function renderHistoryQueue(items) {
  const container = document.getElementById("mobileHistoryList");
  const countEl = document.getElementById("mobileHistoryCount");
  if (countEl) countEl.textContent = items.length;
  if (!container) return;

  if (items.length === 0) {
    container.innerHTML = `<p class="empty-hint">No completed downloads yet.</p>`;
    return;
  }

  container.innerHTML = items.map(item => {
    const isSuccess = item.status === "completed";
    const color = isSuccess ? "var(--accent-green)" : "var(--accent-red)";
    const icon = isSuccess ? "✓" : "✗";

    return `
      <div class="queue-row">
        <div class="queue-row-info">
          <span style="color: ${color}; font-weight: bold; width: 24px; text-align: center;">${icon}</span>
          <div class="queue-row-text">
            <div class="queue-row-title">${escapeHtml(item.name)}</div>
            <div class="queue-row-sub">${item.step} ${item.error ? '&bull; <span style="color: var(--accent-red);">' + escapeHtml(item.error) + '</span>' : ''}</div>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

async function cancelActiveDownload() {
  if (!activeDownloadItem) return;
  const confirmed = confirm(`Cancel downloading ${activeDownloadItem.name}?`);
  if (!confirmed) return;
  vibrate(15);

  try {
    await fetch(`/api/queue/${activeDownloadItem.id}`, { method: "DELETE" });
    showToast("Download cancelled.");
    fetchQueue();
  } catch (e) {
    showToast("Failed to cancel download: " + e.message, true);
  }
}

async function removeQueueItem(itemId) {
  vibrate(10);
  try {
    await fetch(`/api/queue/${itemId}`, { method: "DELETE" });
    fetchQueue();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function clearCompletedQueue() {
  vibrate(10);
  try {
    await fetch("/api/queue/clear-completed", { method: "POST" });
    fetchQueue();
  } catch (e) {}
}

// ---------------- Console & Live Log Streaming ---------------- //
function initSSE() {
  if (sseConnection) sseConnection.close();
  sseConnection = new EventSource("/api/queue/stream");

  sseConnection.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      handleSSEEvent(payload);
    } catch (e) {}
  };

  sseConnection.onerror = () => {
    setTimeout(initSSE, 5000);
  };
}

function handleSSEEvent(payload) {
  const eventType = payload.event;
  const data = payload.data;

  if (eventType === "queue_update") {
    renderQueueState(data);
  } else if (eventType === "item_update") {
    if (activeDownloadItem && activeDownloadItem.id === data.id) {
      renderActiveCard(data);
    }
  } else if (eventType === "item_log") {
    appendConsoleLog(data.line);
  }
}

function appendConsoleLog(line) {
  const term = document.getElementById("mobileTerminalOutput");
  if (!term || !line) return;

  if (term.textContent === "Waiting for SteamCMD activity...") {
    term.textContent = "";
  }

  term.textContent += line + "\n";

  if (autoScrollLogs) {
    term.scrollTop = term.scrollHeight;
  }
}

function toggleAutoScroll() {
  vibrate(10);
  autoScrollLogs = !autoScrollLogs;
  const btn = document.getElementById("mobileAutoScrollBtn");
  if (btn) {
    btn.textContent = `Auto-scroll: ${autoScrollLogs ? 'ON' : 'OFF'}`;
  }
}

function clearConsoleView() {
  vibrate(10);
  const term = document.getElementById("mobileTerminalOutput");
  if (term) term.textContent = "";
}

// ---------------- Settings Management ---------------- //
async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    if (!res.ok) return;
    const s = await res.json();

    const userEl = document.getElementById("mCfgUsername");
    const passEl = document.getElementById("mCfgPassword");
    const platEl = document.getElementById("mCfgPlatform");
    const valEl = document.getElementById("mCfgValidate");
    const goldEl = document.getElementById("mCfgGoldberg");
    const keyEl = document.getElementById("mCfgApiKey");

    if (userEl) userEl.value = s.steamcmd_username || "";
    if (passEl) passEl.value = s.steamcmd_password || "";
    if (platEl) platEl.value = s.force_platform || "windows";
    if (valEl) valEl.checked = s.validate_downloads !== false;
    if (goldEl) goldEl.checked = s.enable_goldberg === true;
    if (keyEl) keyEl.value = s.steam_api_key || "";
  } catch (e) {
    console.warn("Could not load settings:", e);
  }
}

async function saveMobileSettings(event) {
  event.preventDefault();
  vibrate(15);

  const payload = {
    steam_api_key: document.getElementById("mCfgApiKey")?.value || "",
    force_platform: document.getElementById("mCfgPlatform")?.value || "windows",
    validate_downloads: document.getElementById("mCfgValidate")?.checked ?? true,
    enable_goldberg: document.getElementById("mCfgGoldberg")?.checked ?? false,
    steamcmd_username: document.getElementById("mCfgUsername")?.value || "",
    steamcmd_password: document.getElementById("mCfgPassword")?.value || ""
  };

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("Failed to save settings");
    showToast("Settings saved successfully! ✅");
  } catch (e) {
    showToast(e.message, true);
  }
}

async function updateSettingsAuthStatus() {
  const badge = document.getElementById("mCfgAuthBadge");
  if (!badge) return;

  try {
    const res = await fetch("/api/auth/steamcmd/status");
    if (!res.ok) return;
    const data = await res.json();

    if (data.authorized) {
      badge.textContent = "Authorized ✅";
      badge.style.color = "var(--accent-green)";
      badge.style.background = "rgba(34, 197, 94, 0.15)";
    } else {
      badge.textContent = "Not Authorized";
      badge.style.color = "var(--accent-yellow)";
      badge.style.background = "rgba(245, 158, 11, 0.15)";
    }
  } catch (e) {}
}

// ---------------- Container Updates ---------------- //
async function checkForUpdates() {
  try {
    const res = await fetch("/api/system/update/check");
    if (!res.ok) return;
    currentUpdateInfo = await res.json();

    const banner = document.getElementById("mobileUpdateBanner");
    const bannerText = document.getElementById("mobileUpdateText");

    if (currentUpdateInfo && currentUpdateInfo.update_available) {
      if (bannerText) {
        bannerText.textContent = `v${currentUpdateInfo.latest_short_sha || 'update'} available!`;
      }
      if (banner) banner.style.display = "flex";
    } else {
      if (banner) banner.style.display = "none";
    }
  } catch (e) {}
}

function dismissUpdateBanner() {
  const banner = document.getElementById("mobileUpdateBanner");
  if (banner) banner.style.display = "none";
}

function openUpdateSheet() {
  vibrate(10);
  const sheet = document.getElementById("mobileUpdateSheet");
  if (!sheet) return;

  const curVer = document.getElementById("mUpdCurVer");
  const latVer = document.getElementById("mUpdLatestVer");
  const msg = document.getElementById("mUpdCommitMsg");
  const autoSec = document.getElementById("mUpdAutoSec");
  const manSec = document.getElementById("mUpdManualSec");

  if (currentUpdateInfo) {
    if (curVer) curVer.textContent = currentUpdateInfo.current_short_sha || "v1.0.0";
    if (latVer) latVer.textContent = currentUpdateInfo.latest_short_sha || "latest";
    if (msg) msg.textContent = currentUpdateInfo.commit_message || "Latest release updates";
    if (currentUpdateInfo.can_auto_update) {
      if (autoSec) autoSec.style.display = "block";
      if (manSec) manSec.style.display = "none";
    } else {
      if (autoSec) autoSec.style.display = "none";
      if (manSec) manSec.style.display = "block";
    }
  }

  sheet.style.display = "flex";
}

function closeUpdateSheet() {
  const sheet = document.getElementById("mobileUpdateSheet");
  if (sheet) sheet.style.display = "none";
}

async function triggerMobileUpdate() {
  const confirmed = confirm("VaporFetch will recreate and update the container. Proceed?");
  if (!confirmed) return;
  vibrate(20);

  closeUpdateSheet();
  showToast("Updating container... Reconnecting soon.");

  try {
    await fetch("/api/system/update/apply", { method: "POST" });
  } catch (e) {}

  setTimeout(() => {
    setInterval(async () => {
      try {
        const ping = await fetch("/api/system/version", { cache: "no-store" });
        if (ping.ok) {
          window.location.reload();
        }
      } catch (e) {}
    }, 2000);
  }, 6000);
}

// ---------------- Helpers ---------------- //
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

