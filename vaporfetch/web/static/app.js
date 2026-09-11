// VaporFetch Frontend Client Application
document.addEventListener("DOMContentLoaded", () => {
  const state = {
    user: null,
    games: [],
    selectedAppIds: new Set(),
    queueState: null,
    settings: {},
    eventSource: null,
  };

  // DOM Elements
  const elements = {
    // Navigation
    tabBtns: document.querySelectorAll(".tab-btn"),
    tabContents: document.querySelectorAll(".tab-content"),
    libraryCountBadge: document.getElementById("libraryCountBadge"),
    queueCountBadge: document.getElementById("queueCountBadge"),

    // Header & User
    streamStatus: document.getElementById("streamStatus"),
    streamStatusText: document.getElementById("streamStatusText"),
    userName: document.getElementById("userName"),
    authBtn: document.getElementById("authBtn"),
    storageFill: document.getElementById("storageFill"),
    storageDetails: document.getElementById("storageDetails"),

    // Library Tab
    searchInput: document.getElementById("searchInput"),
    filterStatus: document.getElementById("filterStatus"),
    platformSelect: document.getElementById("platformSelect"),
    selectAllBtn: document.getElementById("selectAllBtn"),
    deselectAllBtn: document.getElementById("deselectAllBtn"),
    refreshLibraryBtn: document.getElementById("refreshLibraryBtn"),
    backupSelectedBtn: document.getElementById("backupSelectedBtn"),
    backupAllBtn: document.getElementById("backupAllBtn"),
    selectedCount: document.getElementById("selectedCount"),
    manualAppId: document.getElementById("manualAppId"),
    manualAddBtn: document.getElementById("manualAddBtn"),
    gamesGrid: document.getElementById("gamesGrid"),
    gamesLoading: document.getElementById("gamesLoading"),
    gamesEmpty: document.getElementById("gamesEmpty"),
    emptyTitle: document.getElementById("emptyTitle"),
    emptySubtitle: document.getElementById("emptySubtitle"),
    emptyLoginBtn: document.getElementById("emptyLoginBtn"),
    qrEmptyActions: document.getElementById("qrEmptyActions"),
    emptySettingsBtn: document.getElementById("emptySettingsBtn"),
    emptySwitchPasswordBtn: document.getElementById("emptySwitchPasswordBtn"),

    // Downloads Tab
    noActiveDownload: document.getElementById("noActiveDownload"),
    activeDownloadDetails: document.getElementById("activeDownloadDetails"),
    activeGameName: document.getElementById("activeGameName"),
    activeAppId: document.getElementById("activeAppId"),
    activePlatform: document.getElementById("activePlatform"),
    activeSpeed: document.getElementById("activeSpeed"),
    activeEta: document.getElementById("activeEta"),
    activeProgressBar: document.getElementById("activeProgressBar"),
    activePercent: document.getElementById("activePercent"),
    activeByteProgress: document.getElementById("activeByteProgress"),
    cancelActiveBtn: document.getElementById("cancelActiveBtn"),
    queueList: document.getElementById("queueList"),
    queueCount: document.getElementById("queueCount"),
    clearQueueBtn: document.getElementById("clearQueueBtn"),
    historyList: document.getElementById("historyList"),

    // Terminal Tab
    terminalOutput: document.getElementById("terminalOutput"),
    autoScrollCheck: document.getElementById("autoScrollCheck"),
    clearLogsBtn: document.getElementById("clearLogsBtn"),

    // Settings Tab
    settingsForm: document.getElementById("settingsForm"),
    settingDefaultPlatform: document.getElementById("settingDefaultPlatform"),
    settingFolderFormat: document.getElementById("settingFolderFormat"),
    settingValidate: document.getElementById("settingValidate"),
    settingApiKey: document.getElementById("settingApiKey"),

    // Modal
    authModal: document.getElementById("authModal"),
    modalCloseBtn: document.getElementById("modalCloseBtn"),
    authModeTabs: document.getElementById("authModeTabs"),
    authTabPassword: document.getElementById("authTabPassword"),
    authTabQR: document.getElementById("authTabQR"),
    authPanelPassword: document.getElementById("authPanelPassword"),
    authPanelQR: document.getElementById("authPanelQR"),
    qrLoading: document.getElementById("qrLoading"),
    qrImage: document.getElementById("qrImage"),
    qrStatusText: document.getElementById("qrStatusText"),
    qrRefreshBtn: document.getElementById("qrRefreshBtn"),
    qrError: document.getElementById("qrError"),
    qrCancelBtn: document.getElementById("qrCancelBtn"),
    loginStepCredentials: document.getElementById("loginStepCredentials"),
    loginStep2FA: document.getElementById("loginStep2FA"),
    loginStepSuccess: document.getElementById("loginStepSuccess"),
    loginUsername: document.getElementById("loginUsername"),
    loginPassword: document.getElementById("loginPassword"),
    loginSteamGuard: document.getElementById("loginSteamGuard"),
    loginError: document.getElementById("loginError"),
    loginSubmitBtn: document.getElementById("loginSubmitBtn"),
    loginCancelBtn: document.getElementById("loginCancelBtn"),
    twoFactorCode: document.getElementById("twoFactorCode"),
    twoFactorPromptText: document.getElementById("twoFactorPromptText"),
    twoFactorError: document.getElementById("twoFactorError"),
    twoFactorSubmitBtn: document.getElementById("twoFactorSubmitBtn"),
    twoFactorCancelBtn: document.getElementById("twoFactorCancelBtn"),
    loginDoneBtn: document.getElementById("loginDoneBtn"),
    logoutBtn: document.getElementById("logoutBtn"),
    libraryErrorBanner: document.getElementById("libraryErrorBanner"),
    libraryErrorText: document.getElementById("libraryErrorText"),
    viewLogsBtn: document.getElementById("viewLogsBtn"),
  };

  // --- Initialize App ---
  initNavigation();
  initAuth();
  initLibraryControls();
  initQueueControls();
  initSettings();
  initSSE();
  fetchInitialStatus();

  // --- Navigation Tabs ---
  function initNavigation() {
    elements.tabBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetTab = btn.getAttribute("data-tab");
        elements.tabBtns.forEach((b) => b.classList.remove("active"));
        elements.tabContents.forEach((c) => c.classList.remove("active"));

        btn.classList.add("active");
        const content = document.getElementById(targetTab);
        if (content) content.classList.add("active");
      });
    });
  }

  // --- API & Initial Status ---
  async function fetchInitialStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) return;
      const data = await res.json();

      updateStorageUI(data.storage);
      updateUserSession(data.session);

      if (data.session && data.session.logged_in) {
        fetchLibrary();
      } else {
        showEmptyLibraryState();
      }

      if (data.queue_state) {
        updateQueueUI(data.queue_state);
      }
    } catch (e) {
      console.error("Failed to fetch initial status:", e);
    }
  }

  function updateUserSession(session) {
    if (session && session.logged_in && session.username) {
      state.user = session;
      elements.userName.textContent = session.username;
      elements.authBtn.textContent = "Account";
      elements.authBtn.classList.remove("btn-outline");
      elements.authBtn.classList.add("btn-secondary");
    } else {
      state.user = null;
      elements.userName.textContent = "Not Logged In";
      elements.authBtn.textContent = "Login";
      elements.authBtn.classList.add("btn-outline");
      elements.authBtn.classList.remove("btn-secondary");
    }
  }

  function updateStorageUI(storage) {
    if (!storage) return;
    elements.storageDetails.textContent = `${storage.free_gb} GB Free / ${storage.total_gb} GB`;
    elements.storageFill.style.width = `${storage.percent_used}%`;
  }

  // --- Server-Sent Events (Live Updates) ---
  function initSSE() {
    if (state.eventSource) {
      state.eventSource.close();
    }

    const es = new EventSource("/api/events");
    state.eventSource = es;

    es.onopen = () => {
      elements.streamStatus.classList.remove("status-error");
      elements.streamStatus.classList.add("pulse");
      elements.streamStatusText.textContent = "Live Stream";
    };

    es.onerror = () => {
      elements.streamStatus.classList.add("status-error");
      elements.streamStatus.classList.remove("pulse");
      elements.streamStatusText.textContent = "Reconnecting...";
    };

    es.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        handleSSEEvent(msg);
      } catch (err) {
        // Heartbeat or raw text
      }
    };
  }

  function handleSSEEvent(event) {
    if (!event || !event.type) return;

    if (event.type === "progress") {
      updateActiveDownloadProgress(event.data);
    } else if (event.type === "queue_update") {
      updateQueueUI(event.data);
      if (event.data && event.data.storage) {
        updateStorageUI(event.data.storage);
      }
    } else if (event.type === "log") {
      appendTerminalLog(event.data);
    }
  }

  function appendTerminalLog(logLine) {
    const lineElem = document.createElement("div");
    lineElem.className = "terminal-line";
    lineElem.textContent = logLine;
    elements.terminalOutput.appendChild(lineElem);

    if (elements.autoScrollCheck.checked) {
      elements.terminalOutput.scrollTop = elements.terminalOutput.scrollHeight;
    }
  }

  // --- Authentication Modal ---
  function initAuth() {
    elements.authBtn.addEventListener("click", () => {
      openAuthModal();
    });

    elements.emptyLoginBtn.addEventListener("click", () => {
      openAuthModal();
    });

    elements.emptySettingsBtn?.addEventListener("click", () => {
      document.querySelector('[data-tab="settingsTab"]')?.click();
      elements.settingApiKey?.focus();
    });

    elements.emptySwitchPasswordBtn?.addEventListener("click", () => {
      openAuthModal();
      elements.authTabPassword?.click();
    });

    elements.modalCloseBtn.addEventListener("click", closeAuthModal);
    elements.loginCancelBtn.addEventListener("click", closeAuthModal);
    elements.twoFactorCancelBtn.addEventListener("click", closeAuthModal);

    elements.loginSubmitBtn.addEventListener("click", handleLoginSubmit);
    elements.twoFactorSubmitBtn.addEventListener("click", handle2FASubmit);

    // Auth Mode Tabs (Password vs QR Code)
    elements.authTabPassword?.addEventListener("click", () => {
      elements.authTabPassword.classList.add("active");
      elements.authTabQR.classList.remove("active");
      elements.authPanelPassword.style.display = "block";
      elements.authPanelQR.style.display = "none";
      stopQRPolling();
    });

    elements.authTabQR?.addEventListener("click", () => {
      elements.authTabQR.classList.add("active");
      elements.authTabPassword.classList.remove("active");
      elements.authPanelQR.style.display = "block";
      elements.authPanelPassword.style.display = "none";
      startQRLogin();
    });

    elements.qrRefreshBtn?.addEventListener("click", startQRLogin);
    elements.qrCancelBtn?.addEventListener("click", closeAuthModal);

    if (elements.loginSteamGuard) {
      elements.loginSteamGuard.addEventListener("input", (e) => {
        e.target.value = e.target.value.toUpperCase();
        if (e.target.value.trim().length === 5 && elements.loginUsername.value.trim()) {
          handleLoginSubmit();
        }
      });
      elements.loginSteamGuard.addEventListener("keypress", (e) => {
        if (e.key === "Enter") handleLoginSubmit();
      });
    }

    elements.twoFactorCode.addEventListener("input", (e) => {
      e.target.value = e.target.value.toUpperCase();
      if (e.target.value.trim().length === 5) {
        handle2FASubmit();
      }
    });
    elements.twoFactorCode.addEventListener("keypress", (e) => {
      if (e.key === "Enter") handle2FASubmit();
    });

    elements.loginDoneBtn.addEventListener("click", () => {
      closeAuthModal();
      fetchLibrary();
    });

    elements.logoutBtn.addEventListener("click", handleLogout);
  }

  function openAuthModal() {
    elements.authModal.style.display = "flex";
    elements.loginError.style.display = "none";
    elements.twoFactorError.style.display = "none";
    if (elements.qrError) elements.qrError.style.display = "none";
    stopQRPolling();

    if (state.user && state.user.logged_in) {
      if (elements.authModeTabs) elements.authModeTabs.style.display = "none";
      if (elements.authPanelPassword) elements.authPanelPassword.style.display = "none";
      if (elements.authPanelQR) elements.authPanelQR.style.display = "none";
      elements.loginStepSuccess.style.display = "block";
    } else {
      if (elements.authModeTabs) elements.authModeTabs.style.display = "flex";
      if (elements.authTabPassword) elements.authTabPassword.classList.add("active");
      if (elements.authTabQR) elements.authTabQR.classList.remove("active");
      if (elements.authPanelPassword) elements.authPanelPassword.style.display = "block";
      if (elements.authPanelQR) elements.authPanelQR.style.display = "none";
      elements.loginStepCredentials.style.display = "block";
      elements.loginStep2FA.style.display = "none";
      elements.loginStepSuccess.style.display = "none";
      if (elements.loginSteamGuard) elements.loginSteamGuard.value = "";
      elements.loginUsername.focus();
    }
  }

  function closeAuthModal() {
    stopQRPolling();
    elements.authModal.style.display = "none";
  }

  // --- QR Code Login ---
  let qrPollTimer = null;

  async function startQRLogin() {
    stopQRPolling();
    if (!elements.qrLoading || !elements.qrImage) return;

    elements.qrLoading.style.display = "block";
    elements.qrImage.style.display = "none";
    if (elements.qrError) elements.qrError.style.display = "none";
    elements.qrStatusText.textContent = "Connecting to Steam authentication service...";

    try {
      const res = await fetch("/api/login/qr/begin", { method: "POST" });
      const data = await res.json();
      if (!res.ok || data.status === "failed") {
        showQRError(data.detail || data.error || "Failed to generate Steam QR code.");
        elements.qrLoading.style.display = "none";
        return;
      }

      // Generate crisp QR Code image via standard API
      const qrUrl = "https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=8&data=" + encodeURIComponent(data.challenge_url);
      elements.qrImage.src = qrUrl;
      elements.qrImage.onload = () => {
        elements.qrLoading.style.display = "none";
        elements.qrImage.style.display = "block";
        elements.qrStatusText.textContent = "Scan with your Steam Mobile App";
      };

      // Start polling for scan confirmation
      const pollIntervalMs = (data.interval || 3) * 1000;
      qrPollTimer = setInterval(async () => {
        await pollQRStatus(data.client_id, data.request_id);
      }, pollIntervalMs);

    } catch (e) {
      showQRError(`Network error: ${e.message}`);
      elements.qrLoading.style.display = "none";
    }
  }

  async function pollQRStatus(clientId, requestId) {
    try {
      const res = await fetch("/api/login/qr/poll", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_id: clientId, request_id: requestId }),
      });
      if (!res.ok) return;
      const data = await res.json();

      if (data.status === "waiting") {
        if (data.had_remote_interaction) {
          elements.qrStatusText.innerHTML = "📱 <strong>Device scanned!</strong> Tap <em>Sign In</em> on your phone...";
        }
      } else if (data.status === "logged_in") {
        stopQRPolling();
        elements.qrStatusText.textContent = "✅ Signed in successfully!";
        elements.authPanelQR.style.display = "none";
        if (elements.authModeTabs) elements.authModeTabs.style.display = "none";
        elements.loginStepSuccess.style.display = "block";
        fetchInitialStatus();
      } else if (data.status === "expired") {
        stopQRPolling();
        showQRError("QR code expired. Click Refresh to generate a new code.");
        elements.qrStatusText.textContent = "Session expired.";
      } else if (data.status === "failed") {
        stopQRPolling();
        showQRError(data.error || "QR login failed.");
      }
    } catch (e) {
      // Ignore transient network errors during polling
    }
  }

  function stopQRPolling() {
    if (qrPollTimer) {
      clearInterval(qrPollTimer);
      qrPollTimer = null;
    }
  }

  function showQRError(msg) {
    if (!elements.qrError) return;
    elements.qrError.textContent = msg;
    elements.qrError.style.display = "block";
  }

  async function handleLoginSubmit() {
    const username = elements.loginUsername.value.trim();
    const password = elements.loginPassword.value;
    const code = elements.loginSteamGuard ? elements.loginSteamGuard.value.trim() : "";

    if (!username) {
      showLoginError("Please enter your Steam username.");
      return;
    }

    elements.loginSubmitBtn.disabled = true;
    elements.loginSubmitBtn.textContent = "Connecting to SteamCMD...";
    elements.loginError.style.display = "none";

    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password: password || null, code: code || null }),
      });
      const data = await res.json();
      if (!res.ok) {
        showLoginError(data.detail || data.error || "Failed to start login.");
        return;
      }
      let authResult = data;
      if (authResult.status === "authenticating") {
        elements.loginSubmitBtn.textContent = "Connecting to Steam servers...";
        for (let i = 0; i < 20; i++) {
          await new Promise((r) => setTimeout(r, 1000));
          const checkRes = await fetch("/api/login/status");
          if (checkRes.ok) {
            const checkData = await checkRes.json();
            if (checkData.status && checkData.status !== "authenticating") {
              authResult = checkData;
              break;
            }
          }
        }
      }

      if (authResult.status === "awaiting_2fa") {
        elements.loginStepCredentials.style.display = "none";
        elements.loginStep2FA.style.display = "block";
        elements.twoFactorPromptText.textContent = authResult.prompt || "Enter Steam Guard code";
        elements.twoFactorCode.value = "";
        elements.twoFactorCode.focus();
      } else if (authResult.status === "logged_in") {
        elements.loginStepCredentials.style.display = "none";
        elements.loginStepSuccess.style.display = "block";
        fetchInitialStatus();
      } else {
        showLoginError(authResult.error || "Login failed. Please verify credentials.");
      }
    } catch (e) {
      showLoginError(`Network error: ${e.message}`);
    } finally {
      elements.loginSubmitBtn.disabled = false;
      elements.loginSubmitBtn.textContent = "Sign In";
    }
  }

  function showLoginError(msg) {
    elements.loginError.textContent = msg;
    elements.loginError.style.display = "block";
  }

  async function handle2FASubmit() {
    const code = elements.twoFactorCode.value.trim();
    if (!code) {
      elements.twoFactorError.textContent = "Please enter the code.";
      elements.twoFactorError.style.display = "block";
      return;
    }

    elements.twoFactorSubmitBtn.disabled = true;
    elements.twoFactorSubmitBtn.textContent = "Verifying...";
    elements.twoFactorError.style.display = "none";

    try {
      const res = await fetch("/api/login/2fa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = await res.json();

      if (data.status === "logged_in") {
        elements.loginStep2FA.style.display = "none";
        elements.loginStepSuccess.style.display = "block";
        fetchInitialStatus();
      } else {
        elements.twoFactorError.textContent = data.error || "Invalid 2FA code.";
        elements.twoFactorError.style.display = "block";
      }
    } catch (e) {
      elements.twoFactorError.textContent = `Error: ${e.message}`;
      elements.twoFactorError.style.display = "block";
    } finally {
      elements.twoFactorSubmitBtn.disabled = false;
      elements.twoFactorSubmitBtn.textContent = "Verify & Sign In";
    }
  }

  async function handleLogout() {
    try {
      stopQRPolling();
      await fetch("/api/logout", { method: "POST" });
      updateUserSession(null);
      state.games = [];
      renderGames();
      closeAuthModal();
      showEmptyLibraryState();
    } catch (e) {
      console.error("Logout failed:", e);
    }
  }

  // --- Library Management ---
  function initLibraryControls() {
    elements.searchInput.addEventListener("input", renderGames);
    elements.filterStatus.addEventListener("change", renderGames);

    elements.selectAllBtn.addEventListener("click", () => {
      const filtered = getFilteredGames();
      filtered.forEach((g) => state.selectedAppIds.add(g.appid));
      updateSelectedCount();
      renderGames();
    });

    elements.deselectAllBtn.addEventListener("click", () => {
      state.selectedAppIds.clear();
      updateSelectedCount();
      renderGames();
    });

    elements.refreshLibraryBtn.addEventListener("click", async () => {
      elements.refreshLibraryBtn.disabled = true;
      elements.refreshLibraryBtn.textContent = "⏳ Syncing...";
      elements.gamesLoading.classList.remove("hidden");
      try {
        await fetchLibrary(true);
      } finally {
        elements.refreshLibraryBtn.disabled = false;
        elements.refreshLibraryBtn.textContent = "🔄 Sync Steam Library";
        elements.gamesLoading.classList.add("hidden");
      }
    });

    elements.backupSelectedBtn.addEventListener("click", queueSelectedGames);
    elements.backupAllBtn.addEventListener("click", queueAllGames);

    elements.manualAddBtn.addEventListener("click", () => {
      const aid = parseInt(elements.manualAppId.value.trim(), 10);
      if (aid && aid > 0) {
        queueAppId(aid);
        elements.manualAppId.value = "";
      }
    });

    elements.viewLogsBtn?.addEventListener("click", () => {
      document.querySelector('[data-tab="terminalTab"]')?.click();
    });
  }

  let lastSyncError = "";

  function showLibraryError(msg) {
    if (!elements.libraryErrorBanner) return;
    elements.libraryErrorText.textContent = msg;
    elements.libraryErrorBanner.style.display = "flex";
  }

  function hideLibraryError() {
    if (!elements.libraryErrorBanner) return;
    elements.libraryErrorBanner.style.display = "none";
  }

  async function fetchLibrary(forceRefresh = false) {
    elements.gamesLoading.classList.remove("hidden");
    elements.gamesEmpty.classList.add("hidden");
    hideLibraryError();

    try {
      const endpoint = forceRefresh ? "/api/library/refresh" : "/api/library";
      const res = await fetch(endpoint, { method: forceRefresh ? "POST" : "GET" });
      if (!res.ok) throw new Error("Failed to load library");

      const data = await res.json();
      state.games = data.games || [];
      elements.libraryCountBadge.textContent = state.games.length;

      lastSyncError = data.error || "";
      if (data.error && state.games.length === 0) {
        showLibraryError(data.error);
      } else {
        hideLibraryError();
      }

      renderGames();
    } catch (e) {
      console.error("Error fetching library:", e);
      lastSyncError = e.message;
      showLibraryError(e.message);
    } finally {
      elements.gamesLoading.classList.add("hidden");
      if (state.games.length === 0) {
        showEmptyLibraryState();
      }
    }
  }

  function showEmptyLibraryState() {
    elements.gamesGrid.innerHTML = "";
    elements.gamesEmpty.classList.remove("hidden");

    if (state.user && state.user.logged_in) {
      if (state.user.auth_method === "qr" && !state.user.has_api_key) {
        if (elements.emptyTitle) elements.emptyTitle.textContent = "📱 Steam QR Code Login Active";
        if (elements.emptySubtitle) {
          elements.emptySubtitle.innerHTML =
            "You are signed in via Steam Mobile QR Code! Valve's Web API requires a free Steam Web API Key to view your private library, or you can sign in with Password & 2FA to let SteamCMD sync your library directly.";
        }
        if (elements.qrEmptyActions) elements.qrEmptyActions.style.display = "flex";
        if (elements.emptyLoginBtn) elements.emptyLoginBtn.style.display = "none";
      } else {
        if (elements.emptyTitle) elements.emptyTitle.textContent = "No Games Detected";
        if (elements.emptySubtitle) {
          if (lastSyncError) {
            elements.emptySubtitle.innerHTML =
              `<span style="color: #f87171; font-weight: 500; font-size: 1rem;">⚠️ ${escapeHtml(lastSyncError)}</span><br><br>` +
              "Click 'Re-authenticate with Steam' below to enter your Steam credentials, or view 'SteamCMD Logs' in the top bar to inspect output.";
          } else {
            elements.emptySubtitle.textContent =
              "No owned games detected. Click 'Sync Steam Library' above to refresh licenses from SteamCMD, or add an AppID manually.";
          }
        }
        if (elements.qrEmptyActions) elements.qrEmptyActions.style.display = "none";
        if (elements.emptyLoginBtn) {
          elements.emptyLoginBtn.textContent = "Re-authenticate with Steam";
          elements.emptyLoginBtn.style.display = "inline-block";
        }
      }
    } else {
      if (elements.emptyTitle) elements.emptyTitle.textContent = "No Games Found";
      if (elements.emptySubtitle) {
        elements.emptySubtitle.textContent =
          "Log in with your Steam account to discover and backup your game library.";
      }
      if (elements.qrEmptyActions) elements.qrEmptyActions.style.display = "none";
      if (elements.emptyLoginBtn) {
        elements.emptyLoginBtn.textContent = "Log in to Steam";
        elements.emptyLoginBtn.style.display = "inline-block";
      }
    }
  }

  function getFilteredGames() {
    const query = elements.searchInput.value.toLowerCase().trim();
    const statusFilter = elements.filterStatus.value;

    return state.games.filter((game) => {
      const matchesSearch =
        game.name.toLowerCase().includes(query) || String(game.appid).includes(query);
      if (!matchesSearch) return false;

      if (statusFilter === "downloaded") return game.backup_status === "downloaded";
      if (statusFilter === "not_downloaded") return game.backup_status !== "downloaded";
      return true;
    });
  }

  function renderGames() {
    const filtered = getFilteredGames();
    elements.gamesGrid.innerHTML = "";

    if (filtered.length === 0 && state.games.length > 0) {
      elements.gamesGrid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-dim);">No games match your search filters.</div>`;
      return;
    }

    const fragment = document.createDocumentFragment();

    filtered.forEach((game) => {
      const isSelected = state.selectedAppIds.has(game.appid);
      const card = document.createElement("div");
      card.className = `game-card ${isSelected ? "selected" : ""}`;
      card.setAttribute("data-appid", game.appid);

      let statusBadge = "";
      if (game.backup_status === "downloaded") {
        statusBadge = `<span class="game-card-status-pill status-downloaded">Backed Up (${game.backup_size})</span>`;
      } else if (game.backup_status === "incomplete") {
        statusBadge = `<span class="game-card-status-pill status-queued">Incomplete</span>`;
      } else {
        statusBadge = `<span class="game-card-status-pill status-not-downloaded">Not Backed Up</span>`;
      }

      card.innerHTML = `
        <div class="game-card-img-wrapper">
          <label class="game-card-select-overlay">
            <input type="checkbox" class="game-checkbox" ${isSelected ? "checked" : ""}>
          </label>
          <img class="game-card-img" src="${game.image}" alt="${escapeHtml(game.name)}" loading="lazy" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'460\\' height=\\'215\\' viewBox=\\'0 0 460 215\\'><rect width=\\'100%\\' height=\\'100%\\' fill=\\'%23131b2e\\'/><text x=\\'50%\\' y=\\'50%\\' fill=\\'%2364748b\\' font-family=\\'sans-serif\\' font-size=\\'18\\' dominant-baseline=\\'middle\\' text-anchor=\\'middle\\'>${game.appid}</text></svg>'">
          ${statusBadge}
        </div>
        <div class="game-card-body">
          <div class="game-card-title" title="${escapeHtml(game.name)}">${escapeHtml(game.name)}</div>
          <div class="game-card-meta">
            <span>AppID: ${game.appid}</span>
          </div>
          <div class="game-card-actions">
            <button class="btn btn-sm btn-outline quick-backup-btn" style="width: 100%;">
              💾 Backup Game
            </button>
          </div>
        </div>
      `;

      // Checkbox listener
      const checkbox = card.querySelector(".game-checkbox");
      checkbox.addEventListener("change", (e) => {
        if (e.target.checked) {
          state.selectedAppIds.add(game.appid);
          card.classList.add("selected");
        } else {
          state.selectedAppIds.delete(game.appid);
          card.classList.remove("selected");
        }
        updateSelectedCount();
      });

      // Quick backup button
      const quickBtn = card.querySelector(".quick-backup-btn");
      quickBtn.addEventListener("click", () => {
        queueAppId(game.appid, game.name);
      });

      fragment.appendChild(card);
    });

    elements.gamesGrid.appendChild(fragment);
  }

  function updateSelectedCount() {
    const count = state.selectedAppIds.size;
    elements.selectedCount.textContent = count;
    elements.backupSelectedBtn.disabled = count === 0;
  }

  async function queueSelectedGames() {
    const appids = Array.from(state.selectedAppIds);
    if (appids.length === 0) return;

    const platform = elements.platformSelect.value;
    try {
      const res = await fetch("/api/queue/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ appids, platform }),
      });
      const data = await res.json();
      state.selectedAppIds.clear();
      updateSelectedCount();
      renderGames();

      // Switch to downloads tab
      document.querySelector('[data-tab="downloadsTab"]').click();
    } catch (e) {
      alert(`Error queueing games: ${e.message}`);
    }
  }

  async function queueAllGames() {
    if (!confirm(`Are you sure you want to backup all ${state.games.length} games in your library?`)) {
      return;
    }

    const platform = elements.platformSelect.value;
    try {
      const res = await fetch("/api/queue/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ all_games: true, platform }),
      });
      const data = await res.json();
      alert(data.message || `Queued entire library!`);
      document.querySelector('[data-tab="downloadsTab"]').click();
    } catch (e) {
      alert(`Error queueing library: ${e.message}`);
    }
  }

  async function queueAppId(appid, name = null) {
    const platform = elements.platformSelect.value;
    try {
      const res = await fetch("/api/queue/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ appid, name, platform }),
      });
      const data = await res.json();
      if (data.status === "exists") {
        alert(data.message);
      }
    } catch (e) {
      alert(`Error adding to queue: ${e.message}`);
    }
  }

  // --- Downloads & Queue UI ---
  function initQueueControls() {
    elements.clearQueueBtn.addEventListener("click", async () => {
      if (confirm("Clear all pending games from queue?")) {
        await fetch("/api/queue/clear", { method: "POST" });
      }
    });

    elements.cancelActiveBtn.addEventListener("click", async () => {
      if (confirm("Cancel the current active download?")) {
        await fetch("/api/queue/cancel", { method: "POST" });
      }
    });

    elements.clearLogsBtn.addEventListener("click", () => {
      elements.terminalOutput.innerHTML = "";
    });
  }

  function updateActiveDownloadProgress(task) {
    if (!task) {
      elements.noActiveDownload.style.display = "block";
      elements.activeDownloadDetails.style.display = "none";
      elements.cancelActiveBtn.style.display = "none";
      return;
    }

    elements.noActiveDownload.style.display = "none";
    elements.activeDownloadDetails.style.display = "block";
    elements.cancelActiveBtn.style.display = "inline-block";

    elements.activeGameName.textContent = task.name;
    elements.activeAppId.textContent = `AppID: ${task.appid}`;
    elements.activePlatform.textContent = task.platform;

    elements.activeSpeed.textContent = task.speed_formatted || "--";
    elements.activeEta.textContent = task.eta_seconds > 0 ? `ETA: ${formatDuration(task.eta_seconds)}` : "ETA: --";

    elements.activeProgressBar.style.width = `${task.percent}%`;
    elements.activePercent.textContent = `${task.percent}%`;
    elements.activeByteProgress.textContent = `${task.current_formatted} / ${task.total_formatted}`;
  }

  function updateQueueUI(data) {
    if (!data) return;
    state.queueState = data;

    // Active Task
    updateActiveDownloadProgress(data.current);

    // Queue List
    const queue = data.queue || [];
    elements.queueCount.textContent = queue.length;
    elements.queueCountBadge.textContent = queue.length;

    if (queue.length === 0) {
      elements.queueList.innerHTML = `<div class="empty-queue-msg">The download queue is empty.</div>`;
    } else {
      elements.queueList.innerHTML = "";
      queue.forEach((item) => {
        const itemElem = document.createElement("div");
        itemElem.className = "queue-item";
        itemElem.innerHTML = `
          <div class="queue-item-info">
            <span class="badge badge-platform">${item.platform}</span>
            <span class="queue-item-title">${escapeHtml(item.name)}</span>
            <span class="badge">AppID: ${item.appid}</span>
          </div>
          <div>
            <button class="btn btn-sm btn-danger remove-queue-btn">✕</button>
          </div>
        `;
        itemElem.querySelector(".remove-queue-btn").addEventListener("click", async () => {
          await fetch("/api/queue/remove", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ appid: item.appid }),
          });
        });
        elements.queueList.appendChild(itemElem);
      });
    }

    // History List
    const history = data.history || [];
    if (history.length === 0) {
      elements.historyList.innerHTML = `<div style="text-align: center; color: var(--text-dim); padding: 12px;">No past downloads yet.</div>`;
    } else {
      elements.historyList.innerHTML = "";
      history.forEach((item) => {
        const hElem = document.createElement("div");
        hElem.className = "history-item";
        const isSuccess = item.status === "completed";
        hElem.innerHTML = `
          <div class="queue-item-info">
            <span class="badge" style="background:${isSuccess ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}; color:${isSuccess ? '#10b981' : '#ef4444'}">
              ${item.status.toUpperCase()}
            </span>
            <span class="queue-item-title">${escapeHtml(item.name)}</span>
            <span class="badge">AppID: ${item.appid}</span>
          </div>
          <div style="font-size:0.8rem; color:var(--text-dim)">
            ${item.error ? escapeHtml(item.error) : item.total_formatted}
          </div>
        `;
        elements.historyList.appendChild(hElem);
      });
    }
  }

  // --- Settings ---
  function initSettings() {
    fetchSettings();

    elements.settingsForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const updates = {
        default_platform: elements.settingDefaultPlatform.value,
        folder_format: elements.settingFolderFormat.value,
        validate_downloads: elements.settingValidate.checked,
        steam_api_key: elements.settingApiKey.value.trim(),
      };

      try {
        const res = await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updates),
        });
        if (res.ok) {
          alert("Settings saved successfully!");
          if (updates.steam_api_key) {
            if (state.user) state.user.has_api_key = true;
            fetchLibrary(true);
          }
        }
      } catch (err) {
        alert(`Failed to save settings: ${err.message}`);
      }
    });
  }

  async function fetchSettings() {
    try {
      const res = await fetch("/api/settings");
      if (!res.ok) return;
      const data = await res.json();
      state.settings = data;

      if (data.default_platform) {
        elements.settingDefaultPlatform.value = data.default_platform;
        elements.platformSelect.value = data.default_platform;
      }
      if (data.folder_format) elements.settingFolderFormat.value = data.folder_format;
      if (data.validate_downloads !== undefined) elements.settingValidate.checked = data.validate_downloads;
      if (data.steam_api_key) elements.settingApiKey.value = data.steam_api_key;
    } catch (e) {
      console.error("Failed to load settings:", e);
    }
  }

  // Utilities
  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[m]);
  }

  function formatDuration(sec) {
    if (sec < 60) return `${sec}s`;
    const min = Math.floor(sec / 60);
    const s = sec % 60;
    if (min < 60) return `${min}m ${s}s`;
    const hrs = Math.floor(min / 60);
    return `${hrs}h ${min % 60}m`;
  }
});

