const express = require('express');
const path = require('path');
const fs = require('fs');
const Downloader = require('./src/downloader');
const LibraryManager = require('./src/library');
const { getStorageInfo, listSubdirectories } = require('./src/disk');
const { getAppInfo, getPresets } = require('./src/steamApi');

const app = express();
const PORT = parseInt(process.env.PORT || '8080', 10);
const DOWNLOADS_DIR = process.env.DOWNLOADS_DIR || '/downloads';
const CONFIG_DIR = process.env.CONFIG_DIR || '/config';

// Ensure directories exist
try {
  if (!fs.existsSync(DOWNLOADS_DIR)) fs.mkdirSync(DOWNLOADS_DIR, { recursive: true });
  if (!fs.existsSync(CONFIG_DIR)) fs.mkdirSync(CONFIG_DIR, { recursive: true });
} catch (err) {
  console.warn(`[Startup Warning] Failed creating directory: ${err.message}`);
}

const downloader = new Downloader({
  downloadsDir: DOWNLOADS_DIR,
  configDir: CONFIG_DIR,
  steamCmdPath: process.env.STEAMCMD_PATH || 'steamcmd'
});

const libraryManager = new LibraryManager({
  configDir: CONFIG_DIR,
  downloadsDir: DOWNLOADS_DIR
});

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));

// Server-Sent Events (SSE) Client Connections
const sseClients = new Set();

function broadcastEvent(eventName, payload) {
  const data = `event: ${eventName}\ndata: ${JSON.stringify(payload)}\n\n`;
  for (const res of sseClients) {
    try {
      res.write(data);
    } catch (e) {
      sseClients.delete(res);
    }
  }
}

// Attach Downloader event listeners
downloader.on('log', (logEntry) => {
  broadcastEvent('log', logEntry);
});

downloader.on('status', (statusObj) => {
  broadcastEvent('status', statusObj);
});

downloader.on('steamguard_required', (payload) => {
  broadcastEvent('steamguard', payload);
});

downloader.on('complete', (payload) => {
  broadcastEvent('complete', payload);
});

// SSE Stream Endpoint
app.get('/api/stream', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no' // Prevent Nginx / reverse proxy buffering
  });

  res.write(': connected\n\n');

  // Send initial state
  res.write(`event: status\ndata: ${JSON.stringify(downloader.getStatus())}\n\n`);

  // Send recent log history
  for (const log of downloader.logHistory) {
    res.write(`event: log\ndata: ${JSON.stringify(log)}\n\n`);
  }

  sseClients.add(res);

  // Heartbeat ping every 15s to keep connection alive through NAT/proxies
  const heartbeat = setInterval(() => {
    try {
      res.write(': ping\n\n');
    } catch (err) {
      clearInterval(heartbeat);
      sseClients.delete(res);
    }
  }, 15000);

  req.on('close', () => {
    clearInterval(heartbeat);
    sseClients.delete(res);
  });
});

// Current status and storage info
app.get('/api/status', async (req, res) => {
  try {
    const status = downloader.getStatus();
    const storage = await getStorageInfo(DOWNLOADS_DIR);
    res.json({
      ...status,
      storage,
      serverTime: new Date().toISOString(),
      defaultUser: process.env.STEAM_USERNAME ? 'Configured' : null
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Storage and directory inspection
app.get('/api/storage', async (req, res) => {
  try {
    const storage = await getStorageInfo(DOWNLOADS_DIR);
    const subdirectories = await listSubdirectories(DOWNLOADS_DIR);
    res.json({
      storage,
      subdirectories
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Presets list
app.get('/api/presets', (req, res) => {
  res.json(getPresets());
});

// Library: Get all games in library
app.get('/api/library', (req, res) => {
  try {
    const library = libraryManager.getLibrary();
    res.json(library);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Library: Add a game
app.post('/api/library', (req, res) => {
  try {
    const game = libraryManager.addGame(req.body);
    res.json({ success: true, game });
  } catch (err) {
    res.status(400).json({ success: false, error: err.message });
  }
});

// Library: Remove a game
app.delete('/api/library/:appId', (req, res) => {
  try {
    libraryManager.removeGame(req.params.appId);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Library: Sync Steam user account
app.post('/api/library/sync', async (req, res) => {
  try {
    const { identifier, apiKey } = req.body;
    const result = await libraryManager.syncSteamLibrary(identifier, apiKey);
    res.json(result);
  } catch (err) {
    res.status(400).json({ success: false, error: err.message });
  }
});

// App Info details
app.get('/api/appinfo/:appId', async (req, res) => {
  try {
    const info = await getAppInfo(req.params.appId);
    res.json(info);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Start a download
app.post('/api/download', async (req, res) => {
  try {
    const result = await downloader.startDownload(req.body);
    res.json({
      success: true,
      message: 'Download started successfully',
      job: downloader.currentJob,
      status: result
    });
  } catch (err) {
    res.status(400).json({
      success: false,
      error: err.message
    });
  }
});

// Cancel active download
app.post('/api/cancel', (req, res) => {
  try {
    const result = downloader.cancelDownload();
    res.json(result);
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Submit 2FA Steam Guard code
app.post('/api/steamguard', (req, res) => {
  try {
    const { code } = req.body;
    const result = downloader.submitSteamGuardCode(code);
    res.json(result);
  } catch (err) {
    res.status(400).json({ success: false, error: err.message });
  }
});

// Download history
app.get('/api/history', (req, res) => {
  res.json(downloader.history);
});

// Clear history
app.delete('/api/history', (req, res) => {
  downloader.history = [];
  downloader.saveHistory();
  res.json({ success: true, message: 'History cleared' });
});

// Health check
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    uptime: process.uptime(),
    activeDownload: !!downloader.activeProcess
  });
});

// Fallback to index.html for Single Page App
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Start Server
if (require.main === module) {
  app.listen(PORT, '0.0.0.0', () => {
    console.log(`====================================================`);
    console.log(`  VaporFetch - SteamCMD NAS Downloader Web UI`);
    console.log(`  Listening on: http://0.0.0.0:${PORT}`);
    console.log(`  Downloads directory: ${DOWNLOADS_DIR}`);
    console.log(`  Config directory:    ${CONFIG_DIR}`);
    console.log(`====================================================`);
  });
}

module.exports = app;

