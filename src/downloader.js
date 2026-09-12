const { spawn } = require('child_process');
const EventEmitter = require('events');
const fs = require('fs');
const path = require('path');
const { formatBytes } = require('./disk');
const { getAppInfo } = require('./steamApi');

class Downloader extends EventEmitter {
  constructor(options = {}) {
    super();
    this.downloadsDir = options.downloadsDir || process.env.DOWNLOADS_DIR || '/downloads';
    this.configDir = options.configDir || process.env.CONFIG_DIR || '/config';
    this.steamCmdPath = options.steamCmdPath || process.env.STEAMCMD_PATH || 'steamcmd';

    this.activeProcess = null;
    this.status = 'idle'; // idle, starting, logging_in, paused_2fa, downloading, validating, completed, error, cancelled
    this.currentJob = null;
    this.logHistory = [];
    this.maxLogs = 1000;

    this.historyFile = path.join(this.configDir, 'download_history.json');
    this.history = this.loadHistory();

    // Speed tracking
    this.lastProgressCheck = 0;
    this.lastBytesCurrent = 0;
    this.currentSpeed = 0;
  }

  loadHistory() {
    try {
      if (fs.existsSync(this.historyFile)) {
        const data = fs.readFileSync(this.historyFile, 'utf8');
        return JSON.parse(data);
      }
    } catch (err) {
      console.warn('Could not read history file:', err.message);
    }
    return [];
  }

  saveHistory() {
    try {
      if (!fs.existsSync(this.configDir)) {
        fs.mkdirSync(this.configDir, { recursive: true });
      }
      fs.writeFileSync(this.historyFile, JSON.stringify(this.history.slice(0, 100), null, 2));
    } catch (err) {
      console.warn('Could not save history file:', err.message);
    }
  }

  appendLog(text, type = 'stdout') {
    const timestamp = new Date().toISOString().substring(11, 19);
    const entry = { timestamp, text: text.replace(/\r/g, ''), type };
    this.logHistory.push(entry);
    if (this.logHistory.length > this.maxLogs) {
      this.logHistory.shift();
    }
    this.emit('log', entry);
  }

  getStatus() {
    return {
      status: this.status,
      job: this.currentJob,
      isDownloading: ['starting', 'logging_in', 'paused_2fa', 'downloading', 'validating'].includes(this.status)
    };
  }

  /**
   * Start a Steam game download using SteamCMD
   * @param {Object} options
   */
  async startDownload(options) {
    if (this.activeProcess) {
      throw new Error('A download task is already currently running.');
    }

    const appId = String(options.appId).trim();
    if (!appId || !/^\d+$/.test(appId)) {
      throw new Error('A valid numeric Steam AppID is required.');
    }

    // Determine subfolder and target directory
    const subfolder = (options.installDir || appId).replace(/[^a-zA-Z0-9_\-./]/g, '').replace(/^\/+/, '');
    const fullInstallPath = path.resolve(this.downloadsDir, subfolder);

    // Prevent path traversal outside /downloads
    if (!fullInstallPath.startsWith(path.resolve(this.downloadsDir))) {
      throw new Error('Target folder path is invalid or attempts path traversal.');
    }

    // Ensure directory exists
    try {
      if (!fs.existsSync(fullInstallPath)) {
        fs.mkdirSync(fullInstallPath, { recursive: true });
      }
    } catch (err) {
      throw new Error(`Failed to create target folder on NAS: ${err.message}`);
    }

    // Query app details
    const appInfo = await getAppInfo(appId);
    const appName = appInfo.name || `App ${appId}`;

    const isAnonymous = options.anonymous !== false && options.anonymous !== 'false';
    const username = (options.username || process.env.STEAM_USERNAME || '').trim();
    const password = options.password || process.env.STEAM_PASSWORD || '';
    const steamGuardCode = (options.steamGuardCode || '').trim();
    const validate = options.validate === true || options.validate === 'true';
    const platform = (options.platform || 'auto').toLowerCase();
    const beta = (options.beta || '').trim();
    const betaPassword = (options.betaPassword || '').trim();

    if (!isAnonymous && !username) {
      throw new Error('Steam username is required for non-anonymous downloads.');
    }

    this.logHistory = [];
    this.lastProgressCheck = Date.now();
    this.lastBytesCurrent = 0;
    this.currentSpeed = 0;
    this.status = 'starting';

    this.currentJob = {
      id: `job_${Date.now()}`,
      appId,
      appName,
      headerImage: appInfo.headerImage,
      installDir: fullInstallPath,
      subfolder,
      anonymous: isAnonymous,
      username: isAnonymous ? 'anonymous' : username,
      platform,
      validate,
      beta: beta || null,
      startedAt: new Date().toISOString(),
      completedAt: null,
      error: null,
      progress: {
        percent: 0,
        bytesCurrent: 0,
        bytesTotal: 0,
        bytesCurrentFormatted: '0 B',
        bytesTotalFormatted: '0 B',
        speedFormatted: '0 B/s',
        stage: 'Initializing'
      }
    };

    this.appendLog(`[VaporFetch] Starting download for AppID ${appId} ("${appName}")...`, 'system');
    this.appendLog(`[VaporFetch] Target destination: ${fullInstallPath}`, 'system');
    this.emit('status', this.getStatus());

    // Build SteamCMD arguments
    const args = [];

    // Force platform type if specified (e.g. windows, linux, macos)
    if (['windows', 'linux', 'macos'].includes(platform)) {
      args.push(`+@sSteamCmdForcePlatformType`, platform);
      this.appendLog(`[VaporFetch] Platform forced to: ${platform}`, 'system');
    }

    // Force install directory
    args.push('+force_install_dir', fullInstallPath);

    // Authentication
    if (isAnonymous) {
      args.push('+login', 'anonymous');
    } else {
      if (steamGuardCode) {
        args.push('+login', username, password, steamGuardCode);
      } else {
        args.push('+login', username, password);
      }
    }

    // App Update command
    args.push('+app_update', appId);

    if (beta) {
      args.push('-beta', beta);
      if (betaPassword) {
        args.push('-betapassword', betaPassword);
      }
    }

    if (validate) {
      args.push('validate');
    }

    args.push('+quit');

    // Spawn SteamCMD
    this.appendLog(`[VaporFetch] Executing: ${this.steamCmdPath} +force_install_dir "${fullInstallPath}" +login ${isAnonymous ? 'anonymous' : username} +app_update ${appId} ...`, 'system');

    try {
      this.activeProcess = spawn(this.steamCmdPath, args, {
        env: {
          ...process.env,
          HOME: this.configDir,
          // SteamCMD sometimes checks LC_ALL
          LC_ALL: 'C'
        },
        stdio: ['pipe', 'pipe', 'pipe']
      });
    } catch (err) {
      this.status = 'error';
      this.currentJob.error = err.message;
      this.appendLog(`[VaporFetch ERROR] Failed to spawn steamcmd process: ${err.message}`, 'stderr');
      this.finishJob(false, err.message);
      throw err;
    }

    let lineBuffer = '';

    const handleData = (chunk, isStderr = false) => {
      const text = chunk.toString();
      lineBuffer += text;
      const lines = lineBuffer.split('\n');
      lineBuffer = lines.pop(); // keep remainder

      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line) continue;
        this.appendLog(line, isStderr ? 'stderr' : 'stdout');
        this.parseSteamCmdLine(line);
      }
    };

    this.activeProcess.stdout.on('data', (chunk) => handleData(chunk, false));
    this.activeProcess.stderr.on('data', (chunk) => handleData(chunk, true));

    this.activeProcess.on('close', (code, signal) => {
      if (lineBuffer.trim()) {
        this.appendLog(lineBuffer.trim(), 'stdout');
        this.parseSteamCmdLine(lineBuffer.trim());
        lineBuffer = '';
      }

      this.activeProcess = null;

      if (this.status === 'cancelled') {
        this.finishJob(false, 'Download cancelled by user.');
        return;
      }

      if (code === 0 || code === 7) {
        // SteamCMD often exits with 7 upon successful +quit
        if (this.currentJob.progress.percent >= 99 || this.status === 'validating' || this.status === 'downloading') {
          this.currentJob.progress.percent = 100;
          this.currentJob.progress.stage = 'Completed';
          this.status = 'completed';
          this.appendLog(`[VaporFetch] Download completed successfully for AppID ${appId}!`, 'system');
          this.finishJob(true, 'Download completed successfully');
          return;
        }
      }

      const errorMsg = this.currentJob.error || `Process exited with code ${code}${signal ? ` (signal ${signal})` : ''}`;
      this.status = 'error';
      this.appendLog(`[VaporFetch] Process finished with status: ${errorMsg}`, 'system');
      this.finishJob(false, errorMsg);
    });

    this.activeProcess.on('error', (err) => {
      this.activeProcess = null;
      this.status = 'error';
      this.appendLog(`[VaporFetch ERROR] Process error: ${err.message}`, 'stderr');
      this.finishJob(false, err.message);
    });

    return this.getStatus();
  }

  parseSteamCmdLine(line) {
    // 1. Steam Guard / 2FA check
    if (/steam guard code:/i.test(line) || /two-factor code:/i.test(line) || /enter the code/i.test(line)) {
      this.status = 'paused_2fa';
      this.currentJob.progress.stage = 'Waiting for Steam Guard Code';
      this.appendLog('[VaporFetch ACTION REQUIRED] Steam Guard 2FA code is required! Submit your code in the Web UI.', 'system');
      this.emit('steamguard_required', { appId: this.currentJob.appId });
      this.emit('status', this.getStatus());
      return;
    }

    // 2. Login state
    if (/logging in user/i.test(line)) {
      this.status = 'logging_in';
      this.currentJob.progress.stage = 'Logging into Steam...';
      this.emit('status', this.getStatus());
    }

    if (/logged in ok/i.test(line) || /logging in user.*ok/i.test(line)) {
      this.currentJob.progress.stage = 'Logged in successfully';
      this.emit('status', this.getStatus());
    }

    // 3. Progress match: Update state (0x61) : Downloading, progress: 42.50 (3446865920 / 8111222200)
    const progressRegex = /Update state \((0x[0-9a-fA-F]+)\)\s*:\s*([^,]+),\s*progress:\s*([0-9.]+)\s*\(([0-9]+)\s*\/\s*([0-9]+)\)/i;
    const match = line.match(progressRegex);
    if (match) {
      const stateCode = match[1];
      const stageName = match[2].trim();
      const percent = parseFloat(match[3]);
      const currentBytes = parseInt(match[4], 10);
      const totalBytes = parseInt(match[5], 10);

      const now = Date.now();
      const deltaSec = (now - this.lastProgressCheck) / 1000;
      if (deltaSec >= 1 && currentBytes >= this.lastBytesCurrent) {
        this.currentSpeed = (currentBytes - this.lastBytesCurrent) / deltaSec;
        this.lastProgressCheck = now;
        this.lastBytesCurrent = currentBytes;
      }

      this.status = stageName.toLowerCase().includes('validat') ? 'validating' : 'downloading';
      this.currentJob.progress = {
        percent: Math.min(100, isNaN(percent) ? 0 : percent),
        bytesCurrent: currentBytes,
        bytesTotal: totalBytes,
        bytesCurrentFormatted: formatBytes(currentBytes),
        bytesTotalFormatted: formatBytes(totalBytes),
        speedFormatted: `${formatBytes(this.currentSpeed)}/s`,
        stage: stageName
      };

      this.emit('status', this.getStatus());
      return;
    }

    // 4. Success line
    if (/success!\s+app\s+['"]?(\d+)['"]?\s+fully installed/i.test(line)) {
      this.currentJob.progress.percent = 100;
      this.currentJob.progress.stage = 'Installation Verified';
      this.status = 'completed';
      this.emit('status', this.getStatus());
      return;
    }

    // 5. Specific error conditions
    if (/error!\s+failed to install app.*\(no subscription\)/i.test(line)) {
      this.currentJob.error = 'No Subscription: This game requires a Steam account that owns the game license. (Anonymous download is not permitted).';
      this.appendLog(`[VaporFetch ERROR] ${this.currentJob.error}`, 'stderr');
    } else if (/invalid password/i.test(line)) {
      this.currentJob.error = 'Invalid Steam password or username.';
      this.appendLog(`[VaporFetch ERROR] ${this.currentJob.error}`, 'stderr');
    } else if (/login failure/i.test(line)) {
      this.currentJob.error = line;
      this.appendLog(`[VaporFetch ERROR] ${line}`, 'stderr');
    } else if (/disk write failure/i.test(line)) {
      this.currentJob.error = 'Disk write failure. Check NAS storage permissions (PUID/PGID) and available disk space.';
      this.appendLog(`[VaporFetch ERROR] ${this.currentJob.error}`, 'stderr');
    }
  }

  /**
   * Submit Steam Guard 2FA code to running steamcmd process
   * @param {string} code
   */
  submitSteamGuardCode(code) {
    if (!this.activeProcess || this.status !== 'paused_2fa') {
      throw new Error('No active download is currently waiting for a Steam Guard code.');
    }

    const cleanCode = String(code).trim();
    if (!cleanCode) {
      throw new Error('Steam Guard code cannot be empty.');
    }

    this.appendLog('[VaporFetch] Submitting Steam Guard code...', 'system');
    try {
      this.activeProcess.stdin.write(`${cleanCode}\n`);
      this.status = 'logging_in';
      this.currentJob.progress.stage = 'Verifying Steam Guard code...';
      this.emit('status', this.getStatus());
      return { success: true, message: 'Steam Guard code submitted.' };
    } catch (err) {
      throw new Error(`Failed to send code to process: ${err.message}`);
    }
  }

  /**
   * Cancel the current download
   */
  cancelDownload() {
    if (!this.activeProcess) {
      return { success: false, message: 'No active download running.' };
    }

    this.appendLog('[VaporFetch] Abort requested by user. Terminating SteamCMD process...', 'system');
    this.status = 'cancelled';
    this.emit('status', this.getStatus());

    try {
      this.activeProcess.kill('SIGINT');
      setTimeout(() => {
        if (this.activeProcess) {
          try {
            this.activeProcess.kill('SIGKILL');
          } catch (e) {}
        }
      }, 3000);
      return { success: true, message: 'Cancellation signal sent.' };
    } catch (err) {
      return { success: false, message: err.message };
    }
  }

  finishJob(success, message) {
    if (this.currentJob) {
      this.currentJob.completedAt = new Date().toISOString();
      this.currentJob.success = success;
      this.currentJob.resultMessage = message;

      // Add to persistent history
      this.history.unshift({ ...this.currentJob });
      if (this.history.length > 50) {
        this.history = this.history.slice(0, 50);
      }
      this.saveHistory();
    }

    this.emit('complete', { success, message, job: this.currentJob });
    this.emit('status', this.getStatus());
  }
}

module.exports = Downloader;

