// VaporFetch Frontend Client Application
document.addEventListener("DOMContentLoaded", () => {
  const state = {
    user: null,
    games: [],
    selectedAppIds: new Set(),
    queueState: null,
    settings: {},
    eventSource: null,
    gamesOnlyFilter: true,  // True = show only games, False = show all items including DLCs/tools
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
    filterGamesOnlyBtn: document.getElementById("filterGamesOnlyBtn"),
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
    reauthBtn: document.getElementById("reauthBtn"),
    authStatusAlert: document.getElementById("authStatusAlert"),
    authStatusText: document.getElementById("authStatusText"),
    authUsernameDisplay: document.getElementById("authUsernameDisplay"),
    authSteamIdDisplay: document.getElementById("authSteamIdDisplay"),
    authWebStatus: document.getElementById("authWebStatus"),
    authSteamCmdStatus: document.getElementById("authSteamCmdStatus"),
    libraryErrorBanner: document.getElementById("libraryErrorBanner"),
    libraryErrorText: document.getElementById("libraryErrorText"),
    viewLogsBtn: document.getElementById("viewLogsBtn"),
    versionBadge: document.querySelector(".version-badge"),
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

      if (data.version && elements.versionBadge) {
        elements.versionBadge.textContent = data.version.startsWith("v") ? data.version : `v${data.version}`;
      }

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
      if (state.user && state.user.logged_in) {
        state.user = null;
      }
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
    elements.reauthBtn?.addEventListener("click", () => {
      handleLogout().then(() => {
        openAuthModal();
      });
    });

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
        } else if (data.status === "awaiting_2fa") {
          if (data.prompt && elements.pushStatusText) {
            elements.pushStatusText.textContent = data.prompt;
          }
          if (data.two_factor_type !== "mobile_push") {
            stopPushPolling();
            showDirectStep("code");
            if (elements.codePromptText) elements.codePromptText.textContent = data.prompt || "Enter the Steam Guard code sent to your email:";
            elements.twoFactorCodeInput?.focus();
          }
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
    
    elements.filterGamesOnlyBtn.addEventListener("click", () => {
      state.gamesOnlyFilter = !state.gamesOnlyFilter;
      if (state.gamesOnlyFilter) {
        elements.filterGamesOnlyBtn.classList.add("active");
        elements.filterGamesOnlyBtn.textContent = "🎮 Games Only";
      } else {
        elements.filterGamesOnlyBtn.classList.remove("active");
        elements.filterGamesOnlyBtn.textContent = "📦 All Items (incl. DLCs)";
      }
      // Reset selection when filter changes
      state.selectedAppIds.clear();
      updateSelectedCount();
      renderGames();
    });

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

  // --- Client-Side Non-Game Filter (Strict Games Only) ---
  const CLIENT_ALLOWED_GAMES = new Set([4000, 362890]); // Garry's Mod, Black Mesa

  const CLIENT_KNOWN_NON_GAMES = new Set([
    4, 5, 7, 8, 9, 90, 92, 97, 105, 115, 202355, 205, 215, 218, 225, 245, 255, 364, 410, 513, 563, 564, 575, 576, 629, 644, 746,
    760, 761, 764, 765, 766, 767,  // Steam system apps
    635640,  // Half-Life Ownership
    642920, 646170, 646171, 678350, 1004410,  // Freeman Chronicles
    1098290, 1098292, 1098293, 2545650,  // DOOM Eternal partial content
    1092700, 1092710, 1092720, 1092730, 1096710, 1364960, 1373880,  // Hello Neighbor pre-release
    868020, 446750, 650000, 2012840, 2477290, 1089130,  // VR/RTX
    1205330, 1205580, 1222630, 1222631, 1222632, 1222633, 1222634, 1222635, 1222637, 1222638,  // RetroArch cores
    1227440, 1227441, 1227442, 1227443, 1227444, 1227448, 1227449, 1227450, 1227452, 1227453, 1227454, 1227455, 1227456, 1227457, 1227458, 1227459, 1227460, 1227461, 1227463,  // More emulators
    1761270,  // Half-Life MMod
    1840, 17500, 17510, 17520, 17530, 17550, 17570, 17730, 72850, 202690, 217370, 218350, 220700, 221380,
    223710, 223850, 227260, 228980, 235780, 235900, 243750, 244630, 250820, 258380, 280740, 286010, 286080,
    290930, 317400, 323910, 356530, 362870, 363890, 365300, 365670, 367670, 382110, 383730, 388080, 397460,
    400040, 404790, 431730, 431960, 484580, 524390, 587650, 601360, 629520, 679270, 714070, 858210, 896660,
    908520, 961940, 976620, 993090, 1009850, 1014940, 1054830, 1070560, 1079260, 1096900, 1113280, 1118310,
    1173510, 1192380, 1245040, 1391110, 1420170, 1467450, 1493710, 1494460, 1580130, 1583720, 1628350,
    1807930, 1887720, 1905180, 2180100, 2230260, 2348520, 2805730
  ]);

  function isClientNonGame(game) {
    if (!game) return true;
    if (game.is_tool) return true;
    const appid = Number(game.appid);
    if (CLIENT_ALLOWED_GAMES.has(appid)) return false;
    if (CLIENT_KNOWN_NON_GAMES.has(appid)) return true;

    const clean = (game.name || "").trim();
    if (!clean) return true;
    if (clean.startsWith("Steam App ") || clean.startsWith("SteamDB Unknown App")) return true;
    if (/^App\s*#?\d+$/i.test(clean) || /^app_\d+$/i.test(clean)) return true;

    const lower = clean.toLowerCase();

    // Internal Valve / Proton / Steamworks
    if (
      lower === "winui2" ||
      lower === "steam client" ||
      lower === "spacewar" ||
      lower.startsWith("steam client") ||
      lower.startsWith("steam linux runtime") ||
      lower.startsWith("proton ") ||
      lower === "proton" ||
      lower.startsWith("steamworks ") ||
      lower.startsWith("source sdk") ||
      lower.startsWith("steamvr") ||
      lower.startsWith("unreleased ") ||
      lower.startsWith("valve internal ") ||
      lower.startsWith("steam test ") ||
      lower.startsWith("test app ")
    ) {
      return true;
    }

    // DLC detection
    const dlcRegex = /\b(dlc|expansion pack|expansion pass|season pass|annual pass|battle pass|soundtrack|ost|artbook|art book|digital artbook|digital art book|bonus content|bonus pack|skin pack|character pack|costume pack|item pack|weapon pack|content pack|asset pack|upgrade pack|map pack|voice pack|audio pack|music pack|supporter pack|founder pack|founders pack|pre-order bonus|pre-purchase bonus|special content|making of|concept art|behind the scenes|digital content|exclusive content|cosmetic|cosmetics|bundle)\b/i;
    if (dlcRegex.test(lower)) return true;
    if (
      lower.endsWith(" dlc") ||
      lower.endsWith(" (dlc)") ||
      lower.endsWith(" - dlc") ||
      lower.includes("dlc: ") ||
      lower.includes(": dlc") ||
      lower.includes(" dlc -") ||
      lower.includes("deluxe upgrade") ||
      lower.includes("founder upgrade") ||
      lower.includes("supporter upgrade") ||
      lower.includes("deluxe edition content") ||
      lower.includes("add-on support") ||
      lower.includes("addon support") ||
      lower.endsWith(" add-on") ||
      lower.endsWith(" addon") ||
      lower.endsWith(" (add-on)") ||
      lower.endsWith(" (addon)")
    ) {
      return true;
    }

    // Mod detection
    if (
      lower.endsWith(" mod") ||
      lower.endsWith(" mods") ||
      lower.endsWith(" (mod)") ||
      lower.endsWith(" - mod") ||
      lower.includes(": mod") ||
      lower.includes(" mod: ") ||
      lower.includes(" mod - ") ||
      lower.includes("- mod - ") ||
      lower.includes("source mod") ||
      lower.includes("community mod") ||
      lower.includes("workshop mod") ||
      lower.includes("modification")
    ) {
      return true;
    }

    // Software detection
    const softwareRegex = /\b(software|utility|utilities|benchmark|filmmaker|level editor|map editor|world editor|scenario editor)\b/i;
    if (softwareRegex.test(lower)) return true;
    const softwareKeywords = [
      "wallpaper engine", "godot engine", "rpg maker", "gamemaker", "visual novel maker",
      "blender", "aseprite", "soundpad", "voiceattack", "sharex", "lossless scaling",
      "displayfusion", "obs studio", "borderless gaming", "controller companion",
      "virtual desktop", "fpsvr", "3dmark", "pcmark", "vrmark", "ovr advanced settings",
      "xsoverlay", "desktop+", "stop sign vr"
    ];
    for (const sk of softwareKeywords) {
      if (lower.includes(sk)) return true;
    }
    if (lower.endsWith(" driver") || lower.endsWith(" drivers")) return true;

    // Dedicated servers
    if (
      lower.includes("dedicated server") ||
      lower.includes("linux dedicated server") ||
      lower.endsWith(" server") ||
      lower.endsWith(" servers") ||
      lower.includes(" - server") ||
      lower.includes(" server ") ||
      lower.endsWith(" ds")
    ) {
      return true;
    }

    // Depots, SDKs, authoring/publishing tools
    if (
      lower.includes("depot") ||
      lower.includes("authoring tool") ||
      lower.includes("publishing tool") ||
      lower.includes("creation kit") ||
      lower.includes("devkit") ||
      lower.includes("sdk") ||
      lower.includes("redistributable") ||
      lower.includes("translation server") ||
      lower.includes("content system")
    ) {
      return true;
    }

    // Betas, Demos, Alphas, Samples, Tests, Teasers, OSTs, Playtests
    if (
      lower.endsWith(" - beta") ||
      lower.endsWith(" beta") ||
      lower.endsWith(" (beta)") ||
      lower.endsWith(" - test") ||
      lower.endsWith(" test") ||
      lower.endsWith(" (test)") ||
      lower.endsWith(" - alpha") ||
      lower.endsWith(" alpha") ||
      lower.endsWith(" (alpha)") ||
      lower.endsWith(" - demo") ||
      lower.endsWith(" demo") ||
      lower.endsWith(" (demo)") ||
      lower.endsWith(" - teaser") ||
      lower.endsWith(" (teaser)") ||
      lower.endsWith(" teaser") ||
      lower.endsWith(" - sample") ||
      lower.endsWith(" (sample)") ||
      lower.endsWith(" sample") ||
      lower.endsWith(" - prototype") ||
      lower.endsWith(" (prototype)") ||
      lower.endsWith(" prototype") ||
      lower.includes(" public test") ||
      lower.includes(" public beta") ||
      lower.includes(" closed beta") ||
      lower.includes(" open beta") ||
      lower.includes(" test server") ||
      lower.includes(" test branch") ||
      lower.includes(" beta branch") ||
      lower.includes(" ost") ||
      lower.endsWith(" ost") ||
      lower.includes(" (ost)") ||
      lower.includes(" - ost") ||
      lower.includes("playtest") ||
      lower.includes("trailer") ||
      lower.includes(" - pre-alpha") ||
      lower.includes(" pre-alpha") ||
      lower.includes(" (pre-alpha)")
    ) {
      return true;
    }

    // Emulators and emulator cores
    if (
      lower.includes("retroarch") ||
      lower.includes("emulator") ||
      lower.includes("mesen") ||
      lower.includes("sameboy") ||
      lower.includes("beetle psx") ||
      lower.includes("bsnes") ||
      lower.includes("flycast") ||
      lower.includes("nestopia") ||
      lower.includes("tic-80") ||
      lower.includes("easyrpg") ||
      lower.includes("mupen64") ||
      lower.includes("kronos") ||
      lower.includes("stella") ||
      lower.includes("snes9x") ||
      lower.includes("mgba") ||
      lower.includes("genesis plus") ||
      lower.includes("blastem") ||
      lower.includes("caprice32") ||
      lower.includes("vba-m") ||
      lower.includes("neocd") ||
      lower.includes("freeintv") ||
      lower.includes("quicknes") ||
      lower.includes("picodrive") ||
      lower.includes("pcsx") ||
      lower.includes("px68k")
    ) {
      return true;
    }

    // Steam system and platform apps
    if (
      lower.includes("steam cloud") ||
      lower.includes("steam screenshots") ||
      lower.includes("steam workshop") ||
      lower.includes("steam artwork") ||
      lower.includes("remote play") ||
      lower.includes("greenlight") ||
      lower.startsWith("steam ")
    ) {
      return true;
    }

    // Ownership and license markers
    if (
      lower.includes("ownership") ||
      lower.includes("license marker") ||
      lower.includes("registered") ||
      lower.includes(" - ownership")
    ) {
      return true;
    }

    // Client tools and system packages
    if (
      lower.includes("linux client") ||
      lower.endsWith(" client") ||
      lower.endsWith(" (client)")
    ) {
      return true;
    }

    // Dedicated tool keywords
    if (
      lower.endsWith(" tool") ||
      lower.endsWith(" tools") ||
      lower.endsWith(" editor") ||
      lower.endsWith(" viewer") ||
      lower.endsWith(" launcher") ||
      lower.endsWith(" creator") ||
      lower.endsWith(" maker") ||
      lower.includes(" editor -") ||
      lower.includes(" tool -") ||
      lower.includes("benchmarking")
    ) {
      return true;
    }

    // Videos, movies, music, and media content
    const mediaRegex = /\b(video|movie|film|documentary|animation|music video|short film|live action|cinematics?|movie pack|video collection|music album|concert|live performance)\b/i;
    if (mediaRegex.test(lower)) return true;

    return false;
  }

  async function fetchLibrary(forceRefresh = false) {
    elements.gamesLoading.classList.remove("hidden");
    elements.gamesEmpty.classList.add("hidden");
    hideLibraryError();

    try {
      const ts = Date.now();
      const endpoint = forceRefresh ? `/api/library/refresh?_t=${ts}` : `/api/library?_t=${ts}`;
      const res = await fetch(endpoint, {
        method: forceRefresh ? "POST" : "GET",
        headers: { "Cache-Control": "no-cache", "Pragma": "no-cache" }
      });
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
      const isAuthError = lastSyncError && (
        lastSyncError.toLowerCase().includes("credentials") ||
        lastSyncError.toLowerCase().includes("re-authenticate") ||
        lastSyncError.toLowerCase().includes("sign in") ||
        lastSyncError.toLowerCase().includes("not logged")
      );
      if (elements.emptyLoginBtn) {
        if (isAuthError) {
          elements.emptyLoginBtn.textContent = "Sign In to Steam";
          elements.emptyLoginBtn.style.display = "inline-block";
        } else {
          elements.emptyLoginBtn.style.display = "none";
        }
      }
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
      // Apply games-only filter based on toggle
      if (state.gamesOnlyFilter && isClientNonGame(game)) return false;

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

      const safeTitle = (game.name || `App ${game.appid}`).replace(/['"<>]/g, "");
      const shortTitle = safeTitle.length > 26 ? safeTitle.substring(0, 23) + "..." : safeTitle;
      const fallbackSvg = `data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='460' height='215' viewBox='0 0 460 215'><rect width='100%' height='100%' fill='%23131b2e'/><text x='50%' y='45%' fill='%23e2e8f0' font-family='sans-serif' font-size='16' font-weight='bold' dominant-baseline='middle' text-anchor='middle'>${encodeURIComponent(shortTitle)}</text><text x='50%' y='65%' fill='%2364748b' font-family='sans-serif' font-size='13' dominant-baseline='middle' text-anchor='middle'>AppID: ${game.appid}</text></svg>`;

      card.innerHTML = `
        <div class="game-card-img-wrapper">
          <label class="game-card-select-overlay">
            <input type="checkbox" class="game-checkbox" ${isSelected ? "checked" : ""}>
          </label>
          <img class="game-card-img" src="${game.image}" alt="${escapeHtml(game.name)}" loading="lazy" onerror="this.onerror=null;this.src='${fallbackSvg}';">
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
    const count = state.games.length;
    if (!confirm(`Are you sure you want to backup all ${count} games in your library?`)) {
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

