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
    settingCustomSteamId: document.getElementById("settingCustomSteamId"),

    // Modal & Auth
    authModal: document.getElementById("authModal"),
    modalCloseBtn: document.getElementById("modalCloseBtn"),
    modalTabsBar: document.getElementById("modalTabsBar"),
    tabBtnDirect: document.getElementById("tabBtnDirect"),
    tabBtnQR: document.getElementById("tabBtnQR"),
    authPanelDirect: document.getElementById("authPanelDirect"),
    authStepCredentials: document.getElementById("authStepCredentials"),
    loginUsername: document.getElementById("loginUsername"),
    loginPassword: document.getElementById("loginPassword"),
    loginError: document.getElementById("loginError"),
    loginSubmitBtn: document.getElementById("loginSubmitBtn"),
    authStepPush: document.getElementById("authStepPush"),
    pushStatusText: document.getElementById("pushStatusText"),
    cancelPushBtn: document.getElementById("cancelPushBtn"),
    authStepCode: document.getElementById("authStepCode"),
    codePromptText: document.getElementById("codePromptText"),
    twoFactorCodeInput: document.getElementById("twoFactorCodeInput"),
    codeError: document.getElementById("codeError"),
    twoFactorSubmitBtn: document.getElementById("twoFactorSubmitBtn"),
    cancelCodeBtn: document.getElementById("cancelCodeBtn"),
    authStepLoading: document.getElementById("authStepLoading"),
    loginLoadingText: document.getElementById("loginLoadingText"),
    authPanelQR: document.getElementById("authPanelQR"),
    qrLoading: document.getElementById("qrLoading"),
    qrImage: document.getElementById("qrImage"),
    qrStatusText: document.getElementById("qrStatusText"),
    qrRefreshBtn: document.getElementById("qrRefreshBtn"),
    qrError: document.getElementById("qrError"),
    qrCancelBtn: document.getElementById("qrCancelBtn"),
    loginStepSuccess: document.getElementById("loginStepSuccess"),
    loginDoneBtn: document.getElementById("loginDoneBtn"),
    logoutBtn: document.getElementById("logoutBtn"),
    authStatusAlert: document.getElementById("authStatusAlert"),
    authStatusText: document.getElementById("authStatusText"),
    authUsernameDisplay: document.getElementById("authUsernameDisplay"),
    authSteamIdDisplay: document.getElementById("authSteamIdDisplay"),
    authWebStatus: document.getElementById("authWebStatus"),
    authSteamCmdStatus: document.getElementById("authSteamCmdStatus"),
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
      elements.authBtn.textContent = `Account: ${session.username}`;
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
  let qrPollTimer = null;
  let pushPollTimer = null;
  let activeAuthTab = "direct"; // "direct" or "qr"

  function initAuth() {
    elements.authBtn.addEventListener("click", () => {
      openAuthModal();
    });

    elements.emptyLoginBtn?.addEventListener("click", () => {
      openAuthModal();
    });

    elements.emptySettingsBtn?.addEventListener("click", () => {
      document.querySelector('[data-tab="settingsTab"]')?.click();
      elements.settingApiKey?.focus();
    });

    elements.modalCloseBtn?.addEventListener("click", closeAuthModal);
    elements.loginDoneBtn?.addEventListener("click", () => {
      closeAuthModal();
      fetchLibrary();
    });
    elements.logoutBtn?.addEventListener("click", handleLogout);

    // Tab buttons
    elements.tabBtnDirect?.addEventListener("click", () => switchAuthTab("direct"));
    elements.tabBtnQR?.addEventListener("click", () => switchAuthTab("qr"));

    // Direct Login Form
    elements.loginSubmitBtn?.addEventListener("click", handleDirectLogin);
    elements.loginPassword?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") handleDirectLogin();
    });

    // 2FA Code Form
    elements.twoFactorSubmitBtn?.addEventListener("click", handleTwoFactorSubmit);
    elements.twoFactorCodeInput?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") handleTwoFactorSubmit();
    });

    // Cancel buttons
    elements.cancelPushBtn?.addEventListener("click", () => {
      stopPushPolling();
      showDirectStep("credentials");
    });
    elements.cancelCodeBtn?.addEventListener("click", () => {
      showDirectStep("credentials");
    });

    // QR Buttons
    elements.qrCancelBtn?.addEventListener("click", closeAuthModal);
    elements.qrRefreshBtn?.addEventListener("click", startQRLogin);
  }

  function switchAuthTab(tab) {
    activeAuthTab = tab;
    if (tab === "direct") {
      elements.tabBtnDirect?.classList.add("active");
      elements.tabBtnQR?.classList.remove("active");
      if (elements.authPanelDirect) elements.authPanelDirect.style.display = "block";
      if (elements.authPanelQR) elements.authPanelQR.style.display = "none";
      stopQRPolling();
      showDirectStep("credentials");
    } else {
      elements.tabBtnDirect?.classList.remove("active");
      elements.tabBtnQR?.classList.add("active");
      if (elements.authPanelDirect) elements.authPanelDirect.style.display = "none";
      if (elements.authPanelQR) elements.authPanelQR.style.display = "block";
      stopPushPolling();
      startQRLogin();
    }
  }

  function showDirectStep(step) {
    // "credentials", "loading", "push", "code"
    if (elements.authStepCredentials) elements.authStepCredentials.style.display = step === "credentials" ? "block" : "none";
    if (elements.authStepLoading) elements.authStepLoading.style.display = step === "loading" ? "block" : "none";
    if (elements.authStepPush) elements.authStepPush.style.display = step === "push" ? "block" : "none";
    if (elements.authStepCode) elements.authStepCode.style.display = step === "code" ? "block" : "none";
    if (elements.loginError) elements.loginError.style.display = "none";
    if (elements.codeError) elements.codeError.style.display = "none";
  }

  function openAuthModal() {
    elements.authModal.style.display = "flex";
    stopQRPolling();
    stopPushPolling();

    if (state.user && state.user.logged_in) {
      if (elements.modalTabsBar) elements.modalTabsBar.style.display = "none";
      if (elements.authPanelDirect) elements.authPanelDirect.style.display = "none";
      if (elements.authPanelQR) elements.authPanelQR.style.display = "none";
      if (elements.loginStepSuccess) elements.loginStepSuccess.style.display = "block";

      if (elements.authUsernameDisplay) elements.authUsernameDisplay.textContent = state.user.username || "-";
      if (elements.authSteamIdDisplay) elements.authSteamIdDisplay.textContent = state.user.steam_id || "Auto-detected";
      if (elements.authWebStatus) elements.authWebStatus.innerHTML = "<span style='color: #48bb78; font-weight: 600;'>✅ Connected</span>";
      if (elements.authSteamCmdStatus) elements.authSteamCmdStatus.innerHTML = "<span style='color: #48bb78; font-weight: 600;'>✅ Active &amp; Ready</span>";
      if (elements.authStatusAlert) elements.authStatusAlert.className = "alert alert-success";
      if (elements.authStatusText) elements.authStatusText.textContent = `✅ Signed in as ${state.user.username}`;
    } else {
      if (elements.modalTabsBar) elements.modalTabsBar.style.display = "flex";
      if (elements.loginStepSuccess) elements.loginStepSuccess.style.display = "none";
      switchAuthTab("direct");
      setTimeout(() => elements.loginUsername?.focus(), 50);
    }
  }

  function closeAuthModal() {
    stopQRPolling();
    stopPushPolling();
    if (elements.loginPassword) elements.loginPassword.value = "";
    if (elements.twoFactorCodeInput) elements.twoFactorCodeInput.value = "";
    elements.authModal.style.display = "none";
  }

  async function handleDirectLogin() {
    const username = (elements.loginUsername?.value || "").trim();
    const password = elements.loginPassword?.value || "";

    if (!username) {
      showLoginError("Please enter your Steam username.");
      elements.loginUsername?.focus();
      return;
    }
    if (!password) {
      showLoginError("Please enter your Steam password.");
      elements.loginPassword?.focus();
      return;
    }

    showDirectStep("loading");
    if (elements.loginLoadingText) elements.loginLoadingText.textContent = `Logging in user '${username}'...`;

    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();

      if (!res.ok || data.status === "failed") {
        showDirectStep("credentials");
        showLoginError(data.detail || data.error || "Steam login failed. Please check your username and password.");
        return;
      }

      if (data.status === "logged_in") {
        onAuthSuccess();
      } else if (data.status === "awaiting_2fa") {
        if (data.two_factor_type === "mobile_push") {
          showDirectStep("push");
          startPushPolling();
        } else {
          showDirectStep("code");
          if (elements.codePromptText) elements.codePromptText.textContent = data.prompt || "Enter the Steam Guard code sent to your email or mobile app:";
          elements.twoFactorCodeInput?.focus();
        }
      } else if (data.status === "authenticating") {
        showDirectStep("push");
        startPushPolling();
      } else {
        showDirectStep("credentials");
        showLoginError(data.error || "Unexpected login state.");
      }
    } catch (e) {
      showDirectStep("credentials");
      showLoginError(`Network error: ${e.message}`);
    }
  }

  function startPushPolling() {
    stopPushPolling();
    pushPollTimer = setInterval(async () => {
      try {
        const res = await fetch("/api/login/status");
        if (!res.ok) return;
        const data = await res.json();

        if (data.status === "logged_in") {
          stopPushPolling();
          if (elements.pushStatusText) elements.pushStatusText.textContent = "Approval confirmed! Finishing sign-in...";
          setTimeout(() => onAuthSuccess(), 300);
        } else if (data.status === "failed") {
          stopPushPolling();
          showDirectStep("credentials");
          showLoginError(data.error || "Steam confirmation failed or timed out.");
        } else if (data.status === "awaiting_2fa" && data.two_factor_type !== "mobile_push") {
          stopPushPolling();
          showDirectStep("code");
          if (elements.codePromptText) elements.codePromptText.textContent = data.prompt || "Enter the Steam Guard code sent to your email:";
          elements.twoFactorCodeInput?.focus();
        }
      } catch (e) {
        // Ignore transient poll errors
      }
    }, 1000);
  }

  function stopPushPolling() {
    if (pushPollTimer) {
      clearInterval(pushPollTimer);
      pushPollTimer = null;
    }
  }

  async function handleTwoFactorSubmit() {
    const code = (elements.twoFactorCodeInput?.value || "").trim();
    if (!code) {
      showCodeError("Please enter your Steam Guard code.");
      return;
    }

    if (elements.twoFactorSubmitBtn) {
      elements.twoFactorSubmitBtn.disabled = true;
      elements.twoFactorSubmitBtn.textContent = "Verifying...";
    }

    try {
      const res = await fetch("/api/login/2fa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = await res.json();

      if (!res.ok || data.status === "failed") {
        showCodeError(data.detail || data.error || "Invalid code. Please try again.");
        return;
      }

      if (data.status === "logged_in") {
        onAuthSuccess();
      } else {
        showCodeError(data.error || "Verification incomplete. Please try again.");
      }
    } catch (e) {
      showCodeError(`Network error: ${e.message}`);
    } finally {
      if (elements.twoFactorSubmitBtn) {
        elements.twoFactorSubmitBtn.disabled = false;
        elements.twoFactorSubmitBtn.textContent = "Verify Code";
      }
    }
  }

  async function onAuthSuccess() {
    stopPushPolling();
    stopQRPolling();
    if (elements.modalTabsBar) elements.modalTabsBar.style.display = "none";
    if (elements.authPanelDirect) elements.authPanelDirect.style.display = "none";
    if (elements.authPanelQR) elements.authPanelQR.style.display = "none";
    if (elements.loginStepSuccess) elements.loginStepSuccess.style.display = "block";

    await fetchInitialStatus();
    fetchLibrary(false);
  }

  function showLoginError(msg) {
    if (!elements.loginError) return;
    elements.loginError.textContent = msg;
    elements.loginError.style.display = "block";
  }

  function showCodeError(msg) {
    if (!elements.codeError) return;
    elements.codeError.textContent = msg;
    elements.codeError.style.display = "block";
  }

  // --- Steam Mobile QR Code Login ---
  async function startQRLogin() {
    stopQRPolling();
    stopPushPolling();
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
        onAuthSuccess();
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

  async function handleLogout() {
    try {
      stopQRPolling();
      stopPushPolling();
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
      if (elements.emptyTitle) elements.emptyTitle.textContent = "No Games Detected";
      if (elements.emptySubtitle) {
        if (lastSyncError) {
          elements.emptySubtitle.innerHTML =
            `<span style="color: #f87171; font-weight: 500; font-size: 1rem;">⚠️ ${escapeHtml(lastSyncError)}</span><br><br>` +
            "Tip: Ensure your Steam Privacy Settings have <strong>'Game Details' set to Public</strong>, or configure your <strong>Steam Web API Key &amp; Vanity URL</strong> in Settings.";
        } else {
          elements.emptySubtitle.innerHTML =
            "No games found in this library view. Click <strong>'Sync Steam Library'</strong> above, or add your <strong>Steam Web API Key &amp; Custom URL</strong> in Settings.";
        }
      }
      if (elements.qrEmptyActions) elements.qrEmptyActions.style.display = "flex";
      if (elements.emptyLoginBtn) elements.emptyLoginBtn.style.display = "none";
    } else {
      if (elements.emptyTitle) elements.emptyTitle.textContent = "No Games Found";
      if (elements.emptySubtitle) {
        elements.emptySubtitle.textContent =
          "Log in with your Steam Mobile App to discover and backup your game library.";
      }
      if (elements.qrEmptyActions) elements.qrEmptyActions.style.display = "none";
      if (elements.emptyLoginBtn) {
        elements.emptyLoginBtn.textContent = "Log in with Steam Mobile";
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

  function checkSteamCmdAuthBeforeDownload() {
    if (!state.user || !state.user.logged_in) {
      alert("Please log in with your Steam Mobile App first to start backups.");
      openAuthModal();
      return false;
    }
    return true;
  }

  async function queueSelectedGames() {
    if (!checkSteamCmdAuthBeforeDownload()) return;
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
    if (!checkSteamCmdAuthBeforeDownload()) return;
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
    if (!checkSteamCmdAuthBeforeDownload()) return;
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
        custom_steam_id: elements.settingCustomSteamId ? elements.settingCustomSteamId.value.trim() : "",
      };

      try {
        const res = await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updates),
        });
        if (res.ok) {
          alert("Settings saved successfully!");
          if (updates.steam_api_key || updates.custom_steam_id) {
            if (state.user && updates.steam_api_key) state.user.has_api_key = true;
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
      if (data.custom_steam_id && elements.settingCustomSteamId) {
        elements.settingCustomSteamId.value = data.custom_steam_id;
      }
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

