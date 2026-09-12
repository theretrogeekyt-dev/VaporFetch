// VaporFetch - Frontend Application Logic

let currentUser = null;
let allGames = [];
let filteredGames = [];
let selectedGames = new Map(); // appid -> {appid, name}
let activeDownloadItem = null;
let qrPollTimer = null;
let sseConnection = null;

// Initialization
document.addEventListener("DOMContentLoaded", () => {
  checkAuthSession();
  fetchSystemStatus();
  initSSE();
  checkForUpdatesOnStartup();
  // Poll system status periodically (every 30 seconds)
  setInterval(fetchSystemStatus, 30000);
});

// ---------------- Navigation & Tabs ---------------- //

function switchTab(tab) {
  const libBtn = document.getElementById("tabLibraryBtn");
  const queueBtn = document.getElementById("tabQueueBtn");
  const libView = document.getElementById("libraryView");
  const queueView = document.getElementById("queueView");

  if (tab === "library") {
    libBtn.classList.add("active");
    queueBtn.classList.remove("active");
    libView.classList.add("active");
    queueView.classList.remove("active");
  } else {
    queueBtn.classList.add("active");
    libBtn.classList.remove("active");
    queueView.classList.add("active");
    libView.classList.remove("active");
    fetchQueue();
  }
}

// ---------------- Toast Notifications ---------------- //

function showToast(message, isError = false) {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast ${isError ? 'toast-error' : ''}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ---------------- System Status & Storage ---------------- //

async function fetchSystemStatus() {
  try {
    const res = await fetch("/api/system/status");
    if (!res.ok) return;
    const data = await res.json();

    const disk = data.disk || {};
    const totalGB = (disk.total_bytes / (1024 ** 3)).toFixed(1);
    const freeGB = (disk.free_bytes / (1024 ** 3)).toFixed(1);
    const usedPct = disk.used_percent || 0;

    const storageText = document.getElementById("storageText");
    const storageFill = document.getElementById("storageFill");
    if (storageText) storageText.textContent = `${freeGB} / ${totalGB} GB free`;
    if (storageFill) storageFill.style.width = `${usedPct}%`;

    // Fill system info modal details
    const puidEl = document.getElementById("sysPuid");
    const pgidEl = document.getElementById("sysPgid");
    const downDirEl = document.getElementById("sysDownDir");
    const dataDirEl = document.getElementById("sysDataDir");
    if (puidEl) puidEl.textContent = data.puid;
    if (pgidEl) pgidEl.textContent = data.pgid;
    if (downDirEl) downDirEl.textContent = data.download_dir;
    if (dataDirEl) dataDirEl.textContent = data.data_dir;
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
      renderUserProfile(currentUser);

      // Check if one-time password setup is complete
      const banner = document.getElementById("setupBanner");
      if (!data.has_password) {
        if (banner) banner.style.display = "flex";
      } else {
        if (banner) banner.style.display = "none";
      }

      loadLibrary();
    } else {
      currentUser = null;
      renderUnauthenticated();
    }
  } catch (e) {
    renderUnauthenticated();
  }
}

function renderUserProfile(session) {
  document.getElementById("loginBtn").style.display = "none";
  const userCard = document.getElementById("userCard");
  userCard.style.display = "flex";

  const nameEl = document.getElementById("userName");
  const idEl = document.getElementById("userId");
  const avatarEl = document.getElementById("userAvatar");

  nameEl.textContent = session.personaname || session.account_name || "Steam User";
  idEl.textContent = `ID: ${session.steamid || '--'}`;
  avatarEl.src = session.avatar || "data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 24 24%22 fill=%22%2366c0f4%22><circle cx=%2212%22 cy=%2212%22 r=%2210%22/></svg>";

  document.getElementById("authPromptPlaceholder").style.display = "none";
}

function renderUnauthenticated() {
  document.getElementById("loginBtn").style.display = "inline-flex";
  document.getElementById("userCard").style.display = "none";
  document.getElementById("gamesGrid").innerHTML = "";
  document.getElementById("authPromptPlaceholder").style.display = "block";
  document.getElementById("libraryLoading").style.display = "none";
  document.getElementById("libraryEmpty").style.display = "none";
  const banner = document.getElementById("setupBanner");
  if (banner) banner.style.display = "none";
}

async function logout() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
    currentUser = null;
    allGames = [];
    filteredGames = [];
    selectedGames.clear();
    updateBatchBar();
    renderUnauthenticated();
    showToast("Logged out of Steam.");
  } catch (e) {
    showToast("Failed to logout: " + e.message, true);
  }
}

// QR Code Authentication Modal & Polling
function openQrModal() {
  document.getElementById("qrModal").style.display = "flex";
  document.getElementById("qrScanSection").style.display = "block";
  document.getElementById("qrPasswordSection").style.display = "none";
  startQrSession();
}

function openPasswordSetupModal() {
  document.getElementById("qrModal").style.display = "flex";
  document.getElementById("qrScanSection").style.display = "none";
  document.getElementById("qrPasswordSection").style.display = "block";
  if (currentUser) {
    document.getElementById("verifiedUsername").textContent = currentUser.personaname || currentUser.account_name || "Steam User";
  }
  const pwdInput = document.getElementById("oneTimePasswordInput");
  if (pwdInput) {
    pwdInput.value = "";
    pwdInput.focus();
  }
}

function closeQrModal() {
  document.getElementById("qrModal").style.display = "none";
  if (qrPollTimer) {
    clearInterval(qrPollTimer);
    qrPollTimer = null;
  }
}

async function startQrSession() {
  const loading = document.getElementById("qrLoading");
  const container = document.getElementById("qrImageContainer");
  const img = document.getElementById("qrCodeImg");
  const statusText = document.getElementById("qrStatusText");

  document.getElementById("qrScanSection").style.display = "block";
  document.getElementById("qrPasswordSection").style.display = "none";

  loading.style.display = "block";
  container.style.display = "none";
  statusText.textContent = "Generating Steam Guard challenge...";

  if (qrPollTimer) clearInterval(qrPollTimer);

  try {
    const res = await fetch("/api/auth/qr/begin", { method: "POST" });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to initialize QR session");
    }

    const data = await res.json();
    img.src = data.qr_data_url;
    loading.style.display = "none";
    container.style.display = "flex";
    statusText.textContent = "Scan with Steam Mobile app...";

    // Start polling Steam Auth Status
    const intervalSec = Math.max(data.interval || 5, 2.5);
    qrPollTimer = setInterval(() => {
      pollQrStatus(data.client_id, data.request_id);
    }, intervalSec * 1000);

  } catch (e) {
    loading.style.display = "none";
    statusText.textContent = "Error: " + e.message;
    showToast(e.message, true);
  }
}

async function pollQrStatus(clientId, requestId) {
  try {
    const res = await fetch("/api/auth/qr/poll", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId, request_id: requestId })
    });

    if (!res.ok) return;
    const data = await res.json();

    if (data.status === "confirmed") {
      clearInterval(qrPollTimer);
      qrPollTimer = null;

      const session = data.session || {};
      currentUser = session;
      renderUserProfile(session);

      // Transition to Stage 2: Prompt Password
      document.getElementById("verifiedUsername").textContent = session.personaname || session.account_name || "Steam User";
      document.getElementById("qrScanSection").style.display = "none";
      document.getElementById("qrPasswordSection").style.display = "block";

      const pwdInput = document.getElementById("oneTimePasswordInput");
      if (pwdInput) {
        pwdInput.value = "";
        pwdInput.focus();
      }

      showToast("Steam Guard verified! Enter your password to finish setup.");
    } else if (data.had_remote_interaction) {
      document.getElementById("qrStatusText").textContent = "Approval prompt displayed on phone...";
    }
  } catch (e) {
    console.warn("Poll status failed:", e);
  }
}

async function submitOneTimePassword(event) {
  event.preventDefault();
  const pwdInput = document.getElementById("oneTimePasswordInput");
  const password = pwdInput ? pwdInput.value.trim() : "";
  if (!password) return;

  const btn = document.getElementById("savePasswordBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Saving...";
  }

  try {
    const username = currentUser ? currentUser.account_name : "";
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        steamcmd_password: password,
        steamcmd_username: username
      })
    });

    if (!res.ok) {
      throw new Error("Failed to save password");
    }

    closeQrModal();
    const banner = document.getElementById("setupBanner");
    if (banner) banner.style.display = "none";

    showToast("One-time setup complete! Ready for batch downloads.");
    checkAuthSession();
  } catch (e) {
    showToast(e.message, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Save Password & Open Library";
    }
  }
}

function skipPasswordSetup() {
  closeQrModal();
  showToast("Skipped password setup. You can set it anytime in Settings.");
  checkAuthSession();
}

function togglePasswordVisibility(inputId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  input.type = input.type === "password" ? "text" : "password";
}

// ---------------- Game Library ---------------- //

async function loadLibrary() {
  const loading = document.getElementById("libraryLoading");
  const empty = document.getElementById("libraryEmpty");
  const grid = document.getElementById("gamesGrid");

  loading.style.display = "block";
  empty.style.display = "none";
  grid.innerHTML = "";

  try {
    const res = await fetch("/api/games");
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Could not fetch games");
    }

    const data = await res.json();
    allGames = data.games || [];
    filteredGames = [...allGames];

    loading.style.display = "none";
    if (allGames.length === 0) {
      empty.style.display = "block";
    } else {
      handleSort();
    }
  } catch (e) {
    loading.style.display = "none";
    showToast(e.message, true);
  }
}

function handleSearch() {
  const query = document.getElementById("searchInput").value.trim().toLowerCase();
  const clearBtn = document.getElementById("clearSearchBtn");
  clearBtn.style.display = query ? "block" : "none";

  if (!query) {
    filteredGames = [...allGames];
  } else {
    filteredGames = allGames.filter(g => 
      g.name.toLowerCase().includes(query) || String(g.appid).includes(query)
    );
  }

  handleSort(false);
}

function clearSearch() {
  document.getElementById("searchInput").value = "";
  handleSearch();
}

function handleSort(rerender = true) {
  const sortVal = document.getElementById("sortSelect").value;

  filteredGames.sort((a, b) => {
    switch (sortVal) {
      case "name_asc":
        return a.name.localeCompare(b.name);
      case "name_desc":
        return b.name.localeCompare(a.name);
      case "playtime_desc":
        return b.playtime_forever - a.playtime_forever;
      case "appid_asc":
        return a.appid - b.appid;
      default:
        return 0;
    }
  });

  renderGames();
}

function renderGames() {
  const grid = document.getElementById("gamesGrid");
  const empty = document.getElementById("libraryEmpty");

  if (filteredGames.length === 0 && allGames.length > 0) {
    grid.innerHTML = "";
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";

  const html = filteredGames.map(game => {
    const isSelected = selectedGames.has(game.appid);
    const playtimeHours = (game.playtime_forever / 60).toFixed(1);
    const playtimeStr = game.playtime_forever > 0 ? `${playtimeHours} hrs` : "Unplayed";

    return `
      <div class="game-card ${isSelected ? 'selected' : ''}" 
           id="game-card-${game.appid}" 
           onclick="toggleGameCard(event, ${game.appid}, '${escapeHtml(game.name)}')">
        <div class="game-banner-box">
          <input type="checkbox" 
                 class="game-select-checkbox" 
                 ${isSelected ? 'checked' : ''} 
                 onclick="event.stopPropagation(); toggleGameSelect(${game.appid}, '${escapeHtml(game.name)}', this.checked)">
          <img class="game-banner" 
               src="${game.header_url}" 
               alt="${escapeHtml(game.name)}" 
               loading="lazy"
               onerror="this.onerror=null; this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 460 215%22 fill=%22%23172033%22><rect width=%22100%25%22 height=%22100%25%22/><text x=%2250%25%22 y=%2250%25%22 fill=%22%2366c0f4%22 font-family=%22sans-serif%22 font-size=%2222%22 text-anchor=%22middle%22 dominant-baseline=%22middle%22>${escapeHtml(game.name)}</text></svg>'">
        </div>
        <div class="game-details">
          <div class="game-title" title="${escapeHtml(game.name)}">${escapeHtml(game.name)}</div>
          <div class="game-meta">
            <span>AppID: ${game.appid}</span>
            <span>${playtimeStr}</span>
          </div>
        </div>
      </div>
    `;
  }).join("");

  grid.innerHTML = html;
  updateSelectionUI();
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function toggleGameCard(event, appid, name) {
  // If clicking on links/buttons, return
  if (event.target.tagName === "INPUT") return;
  const isSelected = selectedGames.has(appid);
  toggleGameSelect(appid, name, !isSelected);
}

function toggleGameSelect(appid, name, shouldSelect) {
  if (shouldSelect) {
    selectedGames.set(appid, { appid, name });
  } else {
    selectedGames.delete(appid);
  }

  const card = document.getElementById(`game-card-${appid}`);
  if (card) {
    if (shouldSelect) {
      card.classList.add("selected");
    } else {
      card.classList.remove("selected");
    }
    const checkbox = card.querySelector(".game-select-checkbox");
    if (checkbox) checkbox.checked = shouldSelect;
  }

  updateSelectionUI();
}

function selectAllFiltered() {
  filteredGames.forEach(g => {
    selectedGames.set(g.appid, { appid: g.appid, name: g.name });
  });
  renderGames();
}

function deselectAll() {
  selectedGames.clear();
  renderGames();
}

function updateSelectionUI() {
  const count = selectedGames.size;
  const countBadge = document.getElementById("selectedCount");
  const floatingCount = document.getElementById("floatingSelectedCount");
  const dlBtn = document.getElementById("downloadSelectedBtn");
  const batchBar = document.getElementById("batchActionBar");

  if (countBadge) countBadge.textContent = count;
  if (floatingCount) floatingCount.textContent = count;
  if (dlBtn) dlBtn.disabled = count === 0;

  if (batchBar) {
    batchBar.style.display = count > 0 ? "block" : "none";
  }
}

// ---------------- Download Queue Manager ---------------- //

async function queueSelectedGames() {
  if (selectedGames.size === 0) return;

  const gamesToQueue = Array.from(selectedGames.values());
  try {
    const res = await fetch("/api/queue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ games: gamesToQueue })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to add games to queue");
    }

    const data = await res.json();
    showToast(`Added ${data.added_count} game(s) to download queue!`);
    
    // Clear selection
    deselectAll();
    // Switch to queue view to show progress
    switchTab("queue");
  } catch (e) {
    showToast(e.message, true);
  }
}

async function fetchQueue() {
  try {
    const res = await fetch("/api/queue");
    if (!res.ok) return;
    const data = await res.json();
    renderQueue(data);
  } catch (e) {
    console.warn("Failed to fetch queue:", e);
  }
}

function renderQueue(data) {
  const items = data.items || [];
  const activeId = data.active_id;

  const activeItem = items.find(i => i.status === "running" || i.id === activeId);
  const pendingItems = items.filter(i => i.status === "queued");
  const historyItems = items.filter(i => ["completed", "failed", "cancelled"].includes(i.status));

  // Update tab badge
  const badge = document.getElementById("queueBadge");
  const activeAndPendingCount = (activeItem ? 1 : 0) + pendingItems.length;
  if (badge) {
    badge.textContent = activeAndPendingCount;
    badge.style.display = activeAndPendingCount > 0 ? "inline-block" : "none";
  }

  // Render Active Download
  renderActiveCard(activeItem);

  // Render Pending List
  renderPendingList(pendingItems);

  // Render History List
  renderHistoryList(historyItems);
}

function renderActiveCard(item) {
  const activeSection = document.getElementById("activeDownloadSection");
  if (!item) {
    activeSection.style.display = "none";
    activeDownloadItem = null;
    return;
  }

  activeSection.style.display = "block";
  activeDownloadItem = item;

  document.getElementById("activeGameTitle").textContent = item.name;
  document.getElementById("activeAppId").textContent = `AppID: ${item.appid}`;
  document.getElementById("activeProgressBar").style.width = `${item.progress.toFixed(1)}%`;
  document.getElementById("activeProgressPct").textContent = `${item.progress.toFixed(1)}%`;

  const curMB = (item.current_bytes / (1024 ** 2)).toFixed(1);
  const totMB = (item.total_bytes / (1024 ** 2)).toFixed(1);
  document.getElementById("activeBytes").textContent = `${curMB} MB / ${totMB} MB`;

  const speedMBs = (item.speed_bps / (1024 ** 2)).toFixed(2);
  document.getElementById("activeSpeed").textContent = `${speedMBs} MB/s`;

  document.getElementById("activeEta").textContent = formatEta(item.eta_seconds);
  document.getElementById("activeStep").textContent = item.step;

  // Append recent logs if empty
  const consoleEl = document.getElementById("consoleOutput");
  if (consoleEl && item.log_tail && item.log_tail.length > 0) {
    consoleEl.textContent = item.log_tail.join("\n");
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }
}

function formatEta(seconds) {
  if (!seconds || seconds <= 0) return "--";
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const remSec = seconds % 60;
  if (mins < 60) return `${mins}m ${remSec}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

function renderPendingList(items) {
  const container = document.getElementById("pendingList");
  document.getElementById("pendingCount").textContent = items.length;

  if (items.length === 0) {
    container.innerHTML = `<p class="empty-hint">No downloads pending. Select games from the Library to batch-download.</p>`;
    return;
  }

  container.innerHTML = items.map((item, idx) => `
    <div class="queue-item">
      <div class="queue-item-info">
        <span class="queue-order-badge">#${idx + 1}</span>
        <div>
          <div class="queue-item-name">${escapeHtml(item.name)}</div>
          <div class="queue-item-sub">AppID: ${item.appid} &bull; ${item.step}</div>
        </div>
      </div>
      <button class="btn btn-xs btn-outline" onclick="removeQueueItem('${item.id}')" title="Remove from queue">Remove</button>
    </div>
  `).join("");
}

function renderHistoryList(items) {
  const container = document.getElementById("historyList");
  document.getElementById("historyCount").textContent = items.length;

  if (items.length === 0) {
    container.innerHTML = `<p class="empty-hint">No completed downloads yet.</p>`;
    return;
  }

  container.innerHTML = items.map(item => {
    const isCompleted = item.status === "completed";
    const statusColor = isCompleted ? "var(--accent-green)" : "var(--accent-red)";
    const icon = isCompleted ? "✓" : "✗";

    return `
      <div class="queue-item">
        <div class="queue-item-info">
          <span style="color: ${statusColor}; font-weight: bold; min-width: 20px;">${icon}</span>
          <div>
            <div class="queue-item-name">${escapeHtml(item.name)}</div>
            <div class="queue-item-sub">${item.step} ${item.error ? `&bull; ${escapeHtml(item.error)}` : ''}</div>
          </div>
        </div>
        <div style="display:flex; gap: 6px;">
          ${isCompleted ? `<button class="btn btn-xs btn-outline" onclick="manageGameGoldberg(${item.appid}, '${escapeHtml(item.name)}')" title="Configure Offline Play (Goldberg)">Offline Wrapper</button>` : ''}
          ${!isCompleted ? `<button class="btn btn-xs btn-secondary" onclick="retryQueueItem('${item.id}')">Retry</button>` : ''}
          <button class="btn btn-xs btn-outline" onclick="removeQueueItem('${item.id}')">Dismiss</button>
        </div>
      </div>
    `;
  }).join("");
}

async function removeQueueItem(id) {
  try {
    await fetch(`/api/queue/${id}`, { method: "DELETE" });
    fetchQueue();
  } catch (e) {
    showToast("Error removing item: " + e.message, true);
  }
}

async function retryQueueItem(id) {
  try {
    await fetch(`/api/queue/${id}/retry`, { method: "POST" });
    fetchQueue();
  } catch (e) {
    showToast("Error retrying item: " + e.message, true);
  }
}

async function clearCompletedQueue() {
  try {
    await fetch("/api/queue/clear-completed", { method: "POST" });
    fetchQueue();
  } catch (e) {
    showToast("Error clearing completed: " + e.message, true);
  }
}

async function cancelActiveDownload() {
  if (!activeDownloadItem) return;
  if (!confirm(`Cancel download of "${activeDownloadItem.name}"?`)) return;
  removeQueueItem(activeDownloadItem.id);
}

// ---------------- Live Progress via Server-Sent Events (SSE) ---------------- //

function initSSE() {
  if (sseConnection) {
    sseConnection.close();
  }

  sseConnection = new EventSource("/api/queue/stream");

  sseConnection.onmessage = (e) => {
    try {
      const payload = JSON.parse(e.data);
      handleSSEMessage(payload);
    } catch (err) {
      console.warn("Invalid SSE data", err);
    }
  };

  sseConnection.onerror = () => {
    // Retry connection automatically
    setTimeout(initSSE, 5000);
  };
}

function handleSSEMessage(msg) {
  const evt = msg.event;
  const data = msg.data;

  if (evt === "queue_update") {
    renderQueue(data);
  } else if (evt === "item_update") {
    fetchQueue();
  } else if (evt === "item_log") {
    // Update live metrics on active card
    if (activeDownloadItem && activeDownloadItem.id === data.id) {
      const pct = data.progress.toFixed(1);
      document.getElementById("activeProgressBar").style.width = `${pct}%`;
      document.getElementById("activeProgressPct").textContent = `${pct}%`;

      const curMB = (data.current_bytes / (1024 ** 2)).toFixed(1);
      const totMB = (data.total_bytes / (1024 ** 2)).toFixed(1);
      document.getElementById("activeBytes").textContent = `${curMB} MB / ${totMB} MB`;

      const speedMBs = (data.speed_bps / (1024 ** 2)).toFixed(2);
      document.getElementById("activeSpeed").textContent = `${speedMBs} MB/s`;

      document.getElementById("activeEta").textContent = formatEta(data.eta_seconds);
      document.getElementById("activeStep").textContent = data.step;

      const consoleEl = document.getElementById("consoleOutput");
      if (consoleEl && data.line) {
        consoleEl.textContent += (consoleEl.textContent ? "\n" : "") + data.line;
        consoleEl.scrollTop = consoleEl.scrollHeight;
      }
    }
  }
}

function toggleConsole() {
  const wrapper = document.getElementById("consoleWrapper");
  const text = document.getElementById("consoleToggleText");
  if (wrapper.style.display === "none") {
    wrapper.style.display = "block";
    text.textContent = "Hide SteamCMD Log";
    const consoleEl = document.getElementById("consoleOutput");
    if (consoleEl) consoleEl.scrollTop = consoleEl.scrollHeight;
  } else {
    wrapper.style.display = "none";
    text.textContent = "Show SteamCMD Log";
  }
}

function copyConsoleLogs() {
  const consoleEl = document.getElementById("consoleOutput");
  if (consoleEl) {
    navigator.clipboard.writeText(consoleEl.textContent);
    showToast("Terminal logs copied to clipboard!");
  }
}

// ---------------- Settings Modal ---------------- //

async function openSettingsModal() {
  document.getElementById("settingsModal").style.display = "flex";
  try {
    const res = await fetch("/api/settings");
    if (res.ok) {
      const cfg = await res.json();
      document.getElementById("cfgApiKey").value = cfg.steam_api_key || "";
      document.getElementById("cfgPlatform").value = cfg.force_platform || "windows";
      document.getElementById("cfgValidate").checked = cfg.validate_downloads !== false;
      document.getElementById("cfgGoldberg").checked = cfg.enable_goldberg === true;
      document.getElementById("cfgUsername").value = cfg.steamcmd_username || "";
      document.getElementById("cfgPassword").value = cfg.steamcmd_password || "";
      document.getElementById("cfgCustomArgs").value = cfg.custom_steamcmd_args || "";
    }
    checkGoldbergStatus();
  } catch (e) {
    console.warn("Could not load settings:", e);
  }
}

async function checkGoldbergStatus() {
  const badge = document.getElementById("goldbergBinStatus");
  const alertBox = document.getElementById("goldbergMissingAlert");
  if (!badge) return;
  try {
    const res = await fetch("/api/goldberg/status");
    if (res.ok) {
      const data = await res.json();
      if (data.available) {
        badge.innerHTML = '<span style="color:var(--accent-success); font-weight:600;">● Ready</span>';
        if (alertBox) alertBox.style.display = "none";
      } else {
        badge.innerHTML = '<span style="color:var(--accent-danger); font-weight:600;">● Missing</span>';
        if (alertBox) alertBox.style.display = "flex";
      }
    }
  } catch (e) {
    console.warn("Could not check goldberg status:", e);
  }
}

async function downloadGoldbergBinaries() {
  const btn = document.getElementById("btnDownloadGoldberg");
  const origText = btn ? btn.textContent : "Download Now";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Downloading...";
  }
  try {
    const res = await fetch("/api/goldberg/download", { method: "POST" });
    if (res.ok) {
      showToast("Goldberg emulator DLLs downloaded successfully!");
      checkGoldbergStatus();
    } else {
      const err = await res.json();
      showToast(err.detail || "Download failed. Check container internet connection.", true);
    }
  } catch (e) {
    showToast("Download error: " + e.message, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = origText;
    }
  }
}

function closeSettingsModal() {
  document.getElementById("settingsModal").style.display = "none";
}

async function saveSettings(event) {
  event.preventDefault();
  const payload = {
    steam_api_key: document.getElementById("cfgApiKey").value,
    force_platform: document.getElementById("cfgPlatform").value,
    validate_downloads: document.getElementById("cfgValidate").checked,
    enable_goldberg: document.getElementById("cfgGoldberg").checked,
    steamcmd_username: document.getElementById("cfgUsername").value,
    steamcmd_password: document.getElementById("cfgPassword").value,
    custom_steamcmd_args: document.getElementById("cfgCustomArgs").value,
  };

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      throw new Error("Failed to save settings");
    }

    showToast("Settings saved successfully!");
    closeSettingsModal();
    if (currentUser) {
      loadLibrary();
    }
  } catch (e) {
    showToast(e.message, true);
  }
}

async function manageGameGoldberg(appid, name) {
  try {
    const res = await fetch(`/api/games/${appid}/goldberg`);
    if (!res.ok) {
      showToast(`Game folder for ${name} not found in /downloads.`, true);
      return;
    }
    const data = await res.json();
    if (!data.compatible) {
      showToast(`'${name}' does not use steam_api(64).dll. Goldberg is not required or applicable.`, true);
      return;
    }

    if (data.patched) {
      const confirmRevert = confirm(
        `'${name}' is currently equipped with Goldberg offline emulator.\n\nDo you want to REVERT back to authentic Steam DLLs?`
      );
      if (!confirmRevert) return;
      const revRes = await fetch(`/api/games/${appid}/goldberg/revert`, { method: "POST" });
      if (revRes.ok) {
        showToast(`Reverted '${name}' to authentic Steam binaries!`);
        fetchQueue();
      } else {
        const err = await revRes.json();
        alert(`Revert Failed:\n\n${err.detail || "Revert failed"}`);
      }
    } else {
      if (!data.emulator_ready) {
        const wantDownload = confirm(
          `'${name}' is compatible with Goldberg emulator, but the emulator DLLs are not downloaded yet.\n\nWould you like VaporFetch to download them from the official build repository now?`
        );
        if (!wantDownload) return;
        showToast("Downloading Goldberg binaries...");
        const dlRes = await fetch("/api/goldberg/download", { method: "POST" });
        if (!dlRes.ok) {
          const dlErr = await dlRes.json();
          alert(`Download Failed:\n\n${dlErr.detail || "Could not download emulator DLLs"}`);
          return;
        }
        showToast("Goldberg binaries downloaded! Applying offline patch...");
      }

      const confirmPatch = confirm(
        `'${name}' uses standard Steam API DLLs and is compatible!\n\nWould you like to apply the Goldberg offline play wrapper?\n\n• Replaces steam_api(64).dll with emulator\n• Generates steam_appid.txt (${appid})\n• Backs up original DLLs as .orig`
      );
      if (!confirmPatch) return;
      const patchRes = await fetch(`/api/games/${appid}/goldberg/apply`, { method: "POST" });
      if (patchRes.ok) {
        showToast(`Offline wrapper applied successfully to '${name}'!`);
        fetchQueue();
      } else {
        const err = await patchRes.json();
        alert(`Offline Wrapper Failed:\n\n${err.detail || "Patch failed"}`);
      }
    }
  } catch (e) {
    showToast("Error managing offline wrapper: " + e.message, true);
  }
}

// ---------------- Container Update Notification & In-App Updater ---------------- //

let currentUpdateInfo = null;

async function checkForUpdatesOnStartup(force = false) {
  try {
    const res = await fetch(`/api/system/update/check${force ? '?force=true' : ''}`);
    if (!res.ok) return;
    currentUpdateInfo = await res.json();

    const banner = document.getElementById("updateBanner");
    const navBtn = document.getElementById("navUpdateBtn");
    const bannerText = document.getElementById("updateBannerText");

    if (currentUpdateInfo && currentUpdateInfo.update_available) {
      if (navBtn) navBtn.style.display = "flex";
      
      const dismissedCommit = sessionStorage.getItem("vaporfetch_update_dismissed");
      if (dismissedCommit !== currentUpdateInfo.latest_commit && banner && bannerText) {
        bannerText.innerHTML = `VaporFetch <strong>${currentUpdateInfo.latest_short_sha}</strong> is available: <em>${escapeHtml(currentUpdateInfo.commit_message)}</em>`;
        banner.style.display = "flex";
      }
    } else {
      if (banner) banner.style.display = "none";
      if (navBtn) navBtn.style.display = "none";
    }
  } catch (e) {
    console.warn("Could not check for updates:", e);
  }
}

function dismissUpdateBanner() {
  const banner = document.getElementById("updateBanner");
  if (banner) banner.style.display = "none";
  if (currentUpdateInfo && currentUpdateInfo.latest_commit) {
    sessionStorage.setItem("vaporfetch_update_dismissed", currentUpdateInfo.latest_commit);
  }
}

function openUpdateModal() {
  const modal = document.getElementById("updateModal");
  if (!modal) return;

  const currentVerEl = document.getElementById("updCurrentVer");
  const latestVerEl = document.getElementById("updLatestVer");
  const commitMsgEl = document.getElementById("updCommitMsg");
  const commitDateEl = document.getElementById("updCommitDate");
  const commitLinkEl = document.getElementById("updCommitLink");
  const autoSection = document.getElementById("updAutoSection");
  const manualSection = document.getElementById("updManualSection");

  if (currentUpdateInfo) {
    if (currentVerEl) {
      currentVerEl.textContent = `${currentUpdateInfo.current_version} (${currentUpdateInfo.current_short_sha})`;
    }
    if (latestVerEl) {
      latestVerEl.textContent = `${currentUpdateInfo.latest_short_sha || 'latest'}`;
    }
    if (commitMsgEl) {
      commitMsgEl.textContent = currentUpdateInfo.commit_message || "Latest release updates";
    }
    if (commitDateEl) {
      commitDateEl.textContent = currentUpdateInfo.commit_date ? new Date(currentUpdateInfo.commit_date).toLocaleString() : "";
    }
    if (commitLinkEl) {
      commitLinkEl.href = currentUpdateInfo.commit_url || "https://github.com/theretrogeekyt-dev/VaporFetch/commits/main";
    }

    if (currentUpdateInfo.can_auto_update) {
      if (autoSection) autoSection.style.display = "block";
      if (manualSection) manualSection.style.display = "none";
    } else {
      if (autoSection) autoSection.style.display = "none";
      if (manualSection) manualSection.style.display = "block";
    }
  }

  modal.style.display = "flex";
}

function closeUpdateModal() {
  const modal = document.getElementById("updateModal");
  if (modal) modal.style.display = "none";
}

function copyUpdateCommand() {
  const cmd = document.getElementById("updDockerCmd");
  if (!cmd) return;
  navigator.clipboard.writeText(cmd.textContent.trim()).then(() => {
    showToast("Update command copied to clipboard!");
  }).catch(() => {
    showToast("Failed to copy command", true);
  });
}

async function triggerContainerUpdate() {
  const confirmed = confirm(
    "VaporFetch will now pull the latest image and recreate the container.\n\n" +
    "• The web UI will temporarily disconnect while restarting.\n" +
    "• All downloads, sessions, and configurations in /app/data are preserved.\n\n" +
    "Do you want to proceed with the update?"
  );
  if (!confirmed) return;

  closeUpdateModal();

  const overlay = document.getElementById("updatingOverlay");
  const countdownEl = document.getElementById("reconnectCountdown");
  const statusText = document.getElementById("updatingStatusText");
  if (overlay) overlay.style.display = "flex";

  try {
    const res = await fetch("/api/system/update/apply", { method: "POST" });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to trigger update");
    }
  } catch (e) {
    console.warn("Update trigger sent or container terminated early:", e);
  }

  // Start reconnect countdown and polling
  let secondsRemaining = 25;
  if (countdownEl) countdownEl.textContent = secondsRemaining;

  const timer = setInterval(() => {
    secondsRemaining--;
    if (countdownEl) countdownEl.textContent = Math.max(0, secondsRemaining);
  }, 1000);

  // Poll /api/system/version after 8 seconds
  setTimeout(() => {
    const poller = setInterval(async () => {
      try {
        const ping = await fetch("/api/system/version", { cache: "no-store" });
        if (ping.ok) {
          clearInterval(poller);
          clearInterval(timer);
          if (statusText) statusText.textContent = "Container restarted successfully! Reloading web interface...";
          setTimeout(() => {
            window.location.reload();
          }, 1500);
        }
      } catch (err) {
        // Expected while container is restarting
      }
    }, 2000);
  }, 8000);
}


