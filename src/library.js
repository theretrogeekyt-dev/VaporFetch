const fs = require('fs');
const path = require('path');
const https = require('https');
const { spawn } = require('child_process');
const { getAppInfo } = require('./steamApi');

// Built-in catalog of popular games and dedicated servers
const DEFAULT_CATALOG = [
  { appId: '2280', name: 'DOOM + DOOM II', type: 'game', dir: 'doomplusdoom2', platform: 'windows', anonymous: false },
  { appId: '2394010', name: 'Palworld Dedicated Server', type: 'server', dir: 'palworld', platform: 'windows', anonymous: true },
  { appId: '730', name: 'Counter-Strike 2 Dedicated Server', type: 'server', dir: 'cs2', platform: 'linux', anonymous: true },
  { appId: '896660', name: 'Valheim Dedicated Server', type: 'server', dir: 'valheim', platform: 'linux', anonymous: true },
  { appId: '2278520', name: 'Enshrouded Dedicated Server', type: 'server', dir: 'enshrouded', platform: 'windows', anonymous: true },
  { appId: '258550', name: 'Rust Dedicated Server', type: 'server', dir: 'rust', platform: 'linux', anonymous: true },
  { appId: '2430930', name: 'Ark: Survival Ascended Server', type: 'server', dir: 'ark_sa', platform: 'windows', anonymous: true },
  { appId: '380870', name: 'Project Zomboid Dedicated Server', type: 'server', dir: 'zomboid', platform: 'linux', anonymous: true },
  { appId: '2465200', name: 'Sons of the Forest Server', type: 'server', dir: 'sotf', platform: 'windows', anonymous: true },
  { appId: '294420', name: '7 Days to Die Dedicated Server', type: 'server', dir: '7daystodie', platform: 'linux', anonymous: true },
  { appId: '4020', name: "Garry's Mod Dedicated Server", type: 'server', dir: 'gmod', platform: 'linux', anonymous: true },
  { appId: '232250', name: 'Team Fortress 2 Server', type: 'server', dir: 'tf2', platform: 'linux', anonymous: true },
  { appId: '222860', name: 'Left 4 Dead 2 Dedicated Server', type: 'server', dir: 'l4d2', platform: 'linux', anonymous: true },
  { appId: '1690800', name: 'Satisfactory Dedicated Server', type: 'server', dir: 'satisfactory', platform: 'linux', anonymous: true },
  { appId: '1829350', name: 'V Rising Dedicated Server', type: 'server', dir: 'vrising', platform: 'windows', anonymous: true },
  { appId: '105600', name: 'Terraria', type: 'game', dir: 'terraria', platform: 'windows', anonymous: false },
  { appId: '70', name: 'Half-Life', type: 'game', dir: 'halflife', platform: 'windows', anonymous: false },
  { appId: '220', name: 'Half-Life 2', type: 'game', dir: 'hl2', platform: 'windows', anonymous: false },
  { appId: '400', name: 'Portal', type: 'game', dir: 'portal', platform: 'windows', anonymous: false },
  { appId: '620', name: 'Portal 2', type: 'game', dir: 'portal2', platform: 'windows', anonymous: false },
  { appId: '1086940', name: "Baldur's Gate 3", type: 'game', dir: 'bg3', platform: 'windows', anonymous: false },
  { appId: '1245620', name: 'ELDEN RING', type: 'game', dir: 'eldenring', platform: 'windows', anonymous: false },
  { appId: '1091500', name: 'Cyberpunk 2077', type: 'game', dir: 'cyberpunk2077', platform: 'windows', anonymous: false }
];

class LibraryManager {
  constructor(options = {}) {
    this.configDir = options.configDir || process.env.CONFIG_DIR || '/config';
    this.downloadsDir = options.downloadsDir || process.env.DOWNLOADS_DIR || '/downloads';
    this.steamCmdPath = options.steamCmdPath || process.env.STEAMCMD_PATH || 'steamcmd';
    this.libraryFile = path.join(this.configDir, 'user_library.json');
    this.userGames = this.loadUserLibrary();
  }

  loadUserLibrary() {
    try {
      if (fs.existsSync(this.libraryFile)) {
        const data = fs.readFileSync(this.libraryFile, 'utf8');
        return JSON.parse(data);
      }
    } catch (e) {
      console.warn('Could not read user library file:', e.message);
    }
    return [];
  }

  saveUserLibrary() {
    try {
      if (!fs.existsSync(this.configDir)) {
        fs.mkdirSync(this.configDir, { recursive: true });
      }
      fs.writeFileSync(this.libraryFile, JSON.stringify(this.userGames, null, 2));
    } catch (e) {
      console.warn('Could not save user library file:', e.message);
    }
  }

  getLibrary() {
    const map = new Map();

    for (const item of DEFAULT_CATALOG) {
      map.set(item.appId, {
        ...item,
        headerImage: `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${item.appId}/header.jpg`,
        isUserOwned: false
      });
    }

    for (const item of this.userGames) {
      map.set(item.appId, {
        ...item,
        headerImage: item.headerImage || `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${item.appId}/header.jpg`,
        isUserOwned: true
      });
    }

    const installedFolders = new Set();
    try {
      if (fs.existsSync(this.downloadsDir)) {
        const entries = fs.readdirSync(this.downloadsDir, { withFileTypes: true });
        for (const entry of entries) {
          if (entry.isDirectory()) {
            installedFolders.add(entry.name.toLowerCase());
          }
        }
      }
    } catch (e) {}

    const list = Array.from(map.values()).map(game => {
      const targetFolder = (game.dir || game.name.toLowerCase().replace(/[^a-z0-9]+/g, '_')).toLowerCase();
      const isInstalled = installedFolders.has(targetFolder) || installedFolders.has(game.appId);
      return {
        ...game,
        targetFolder,
        isInstalled
      };
    });

    return list.sort((a, b) => a.name.localeCompare(b.name));
  }

  addGame(game) {
    const appId = String(game.appId).trim();
    if (!appId || !/^\d+$/.test(appId)) {
      throw new Error('Valid numeric AppID is required');
    }

    const cleanGame = {
      appId,
      name: game.name || `App ${appId}`,
      dir: game.dir || (game.name || appId).toLowerCase().replace(/[^a-z0-9]+/g, '_'),
      platform: game.platform || 'windows',
      anonymous: game.anonymous === true,
      type: game.type || 'game',
      headerImage: game.headerImage || `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${appId}/header.jpg`
    };

    const existingIndex = this.userGames.findIndex(g => g.appId === appId);
    if (existingIndex >= 0) {
      this.userGames[existingIndex] = cleanGame;
    } else {
      this.userGames.unshift(cleanGame);
    }

    this.saveUserLibrary();
    return cleanGame;
  }

  removeGame(appId) {
    const id = String(appId).trim();
    this.userGames = this.userGames.filter(g => g.appId !== id);
    this.saveUserLibrary();
    return true;
  }

  /**
   * Detect logged-in Steam accounts from local SteamCMD config.vdf, loginusers.vdf, and userdata folders
   */
  detectLocalSteamAccounts() {
    const detected = [];

    // 1. Scan loginusers.vdf files (stores AccountName and SteamID64 for every user that ever logged in)
    const loginUserCandidates = [
      path.join(this.configDir, 'Steam', 'config', 'loginusers.vdf'),
      path.join(this.configDir, '.steam', 'steam', 'config', 'loginusers.vdf'),
      path.join(this.configDir, '.steam', 'config', 'loginusers.vdf'),
      path.join(this.configDir, 'config', 'loginusers.vdf'),
      path.join(this.configDir, 'loginusers.vdf'),
      path.join('/root', 'Steam', 'config', 'loginusers.vdf'),
      path.join('/root', '.steam', 'steam', 'config', 'loginusers.vdf'),
      path.join('/root', '.steam', 'config', 'loginusers.vdf'),
      path.join('/usr/local/steamcmd', 'config', 'loginusers.vdf')
    ];

    for (const file of loginUserCandidates) {
      if (fs.existsSync(file)) {
        try {
          const content = fs.readFileSync(file, 'utf8');
          const userMatches = content.matchAll(/"(\d{17})"\s*\{([^}]+)\}/gi);
          for (const um of userMatches) {
            const steamId64 = um[1];
            const block = um[2];
            const accMatch = block.match(/"AccountName"\s*"([^"]+)"/i);
            const personaMatch = block.match(/"PersonaName"\s*"([^"]+)"/i);
            const accountName = accMatch ? accMatch[1] : `User_${steamId64}`;
            const personaName = personaMatch ? personaMatch[1] : accountName;
            if (!detected.some(d => d.steamId64 === steamId64)) {
              detected.push({
                username: accountName,
                personaName: personaName,
                steamId64: steamId64,
                source: 'Steam login cache (loginusers.vdf)'
              });
            }
          }
        } catch (e) {}
      }
    }

    // 2. Scan config.vdf files
    const configCandidates = [
      path.join(this.configDir, 'Steam', 'config', 'config.vdf'),
      path.join(this.configDir, '.steam', 'steam', 'config', 'config.vdf'),
      path.join(this.configDir, '.steam', 'config', 'config.vdf'),
      path.join(this.configDir, 'config', 'config.vdf'),
      path.join('/root', 'Steam', 'config', 'config.vdf'),
      path.join('/root', '.steam', 'steam', 'config', 'config.vdf'),
      path.join('/usr/local/steamcmd', 'config', 'config.vdf')
    ];

    for (const file of configCandidates) {
      if (fs.existsSync(file)) {
        try {
          const content = fs.readFileSync(file, 'utf8');
          const userBlocks = content.matchAll(/"([^"]+)"\s*\{\s*[^}]*?"SteamID"\s*"(\d{17})"/gi);
          for (const ub of userBlocks) {
            if (!['Software', 'Valve', 'Steam', 'Accounts', 'InstallConfigStore'].includes(ub[1])) {
              if (!detected.some(d => d.steamId64 === ub[2])) {
                detected.push({
                  username: ub[1],
                  personaName: ub[1],
                  steamId64: ub[2],
                  source: 'SteamCMD config.vdf'
                });
              }
            }
          }
        } catch (e) {}
      }
    }

    // 3. Scan userdata folders
    const userdataDirs = [
      path.join(this.configDir, 'Steam', 'userdata'),
      path.join(this.configDir, '.steam', 'steam', 'userdata'),
      path.join(this.configDir, 'userdata'),
      path.join('/root', 'Steam', 'userdata'),
      path.join('/root', '.steam', 'steam', 'userdata'),
      path.join('/usr/local/steamcmd', 'userdata')
    ];

    for (const udir of userdataDirs) {
      if (fs.existsSync(udir)) {
        try {
          const entries = fs.readdirSync(udir, { withFileTypes: true });
          for (const d of entries) {
            if (d.isDirectory() && /^\d+$/.test(d.name) && d.name !== '0') {
              try {
                const accountId32 = BigInt(d.name);
                const steamId64 = (accountId32 + 76561197960265728n).toString();
                let username = `Account (${d.name})`;
                let personaName = `Account (${d.name})`;

                // Try to read PersonaName or AccountName from localconfig.vdf
                const localConfigPath = path.join(udir, d.name, 'config', 'localconfig.vdf');
                if (fs.existsSync(localConfigPath)) {
                  try {
                    const lcTxt = fs.readFileSync(localConfigPath, 'utf8');
                    const pm = lcTxt.match(/"PersonaName"\s*"([^"]+)"/i);
                    const am = lcTxt.match(/"AccountName"\s*"([^"]+)"/i);
                    if (pm) personaName = pm[1];
                    if (am) username = am[1];
                    else if (pm) username = pm[1];
                  } catch (e) {}
                }

                if (!detected.some(acc => acc.steamId64 === steamId64)) {
                  detected.push({
                    username,
                    personaName,
                    steamId64: steamId64,
                    source: 'Steam userdata'
                  });
                }
              } catch (e) {}
            }
          }
        } catch (e) {}
      }
    }

    return detected;
  }

  /**
   * Extract game AppIDs cached in localconfig.vdf and sharedconfig.vdf
   */
  extractGamesFromLocalConfig() {
    const foundAppIds = new Set();
    const userdataDirs = [
      path.join(this.configDir, 'Steam', 'userdata'),
      path.join(this.configDir, '.steam', 'steam', 'userdata'),
      path.join(this.configDir, 'userdata'),
      path.join('/usr/local/steamcmd', 'userdata')
    ];

    for (const udir of userdataDirs) {
      if (!fs.existsSync(udir)) continue;
      try {
        const subdirs = fs.readdirSync(udir, { withFileTypes: true });
        for (const sub of subdirs) {
          if (!sub.isDirectory()) continue;

          // 1. localconfig.vdf
          const localConfig = path.join(udir, sub.name, 'config', 'localconfig.vdf');
          if (fs.existsSync(localConfig)) {
            try {
              const txt = fs.readFileSync(localConfig, 'utf8');
              const matches = txt.matchAll(/"(\d{2,8})"\s*\{/g);
              for (const m of matches) {
                const id = m[1];
                if (parseInt(id, 10) > 100) foundAppIds.add(id);
              }
            } catch (e) {}
          }

          // 2. sharedconfig.vdf
          const sharedConfig = path.join(udir, sub.name, '7', 'remote', 'sharedconfig.vdf');
          if (fs.existsSync(sharedConfig)) {
            try {
              const txt = fs.readFileSync(sharedConfig, 'utf8');
              const matches = txt.matchAll(/"(\d{2,8})"\s*\{/g);
              for (const m of matches) {
                const id = m[1];
                if (parseInt(id, 10) > 100) foundAppIds.add(id);
              }
            } catch (e) {}
          }
        }
      } catch (e) {}
    }

    return Array.from(foundAppIds);
  }

  /**
   * Import games directly from local SteamCMD cached userdata
   */
  async syncFromLocalCache() {
    const appIds = this.extractGamesFromLocalConfig();
    if (!appIds || appIds.length === 0) {
      throw new Error('No game licenses cached locally yet. As you download games with SteamCMD, your library cache will populate here.');
    }

    let addedCount = 0;
    for (const appId of appIds) {
      if (!this.userGames.some(g => g.appId === appId)) {
        const info = await getAppInfo(appId);
        const name = info.name || `App ${appId}`;
        const dir = (name || appId).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');

        this.userGames.push({
          appId,
          name,
          dir,
          type: 'game',
          platform: 'windows',
          anonymous: false,
          headerImage: info.headerImage || `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${appId}/header.jpg`
        });
        addedCount++;
      }
    }

    this.saveUserLibrary();

    return {
      success: true,
      totalImported: appIds.length,
      newlyAdded: addedCount,
      games: this.getLibrary()
    };
  }

  /**
   * Batch import games from a list of AppIDs or text
   */
  async importFromAppIds(text) {
    if (!text || typeof text !== 'string') {
      throw new Error('Please provide text containing Steam AppIDs.');
    }

    const rawMatches = text.match(/\b\d{2,8}\b/g) || [];
    const uniqueIds = Array.from(new Set(rawMatches));

    if (uniqueIds.length === 0) {
      throw new Error('No numeric Steam AppIDs found in the provided text.');
    }

    let addedCount = 0;

    for (const appId of uniqueIds) {
      if (!this.userGames.some(g => g.appId === appId)) {
        const info = await getAppInfo(appId);
        const name = info.name || `App ${appId}`;
        const dir = (name || appId).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');

        this.userGames.push({
          appId,
          name,
          dir,
          type: 'game',
          platform: 'windows',
          anonymous: false,
          headerImage: info.headerImage || `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${appId}/header.jpg`
        });
        addedCount++;
      }
    }

    this.saveUserLibrary();

    return {
      success: true,
      totalImported: uniqueIds.length,
      newlyAdded: addedCount,
      games: this.getLibrary()
    };
  }

  /**
   * Resolve vanity URL or profile link to a numeric 64-bit Steam ID
   */
  async resolveToSteamId64(identifier, apiKey) {
    let clean = String(identifier || '').trim();
    clean = clean.replace(/^https?:\/\/steamcommunity\.com\/(id|profiles)\//i, '').replace(/\/.*$/, '').trim();

    if (/^\d{17}$/.test(clean)) {
      return clean;
    }

    // 1. Check local SteamCMD accounts detected on this container FIRST (0ms latency, handles private login names)
    const localAccounts = this.detectLocalSteamAccounts();
    const matched = localAccounts.find(a => 
      a.username.toLowerCase() === clean.toLowerCase() || 
      (a.personaName && a.personaName.toLowerCase() === clean.toLowerCase()) || 
      a.steamId64 === clean
    );
    if (matched) {
      console.log(`[VaporFetch] Resolved "${clean}" to SteamID64 ${matched.steamId64} via local Steam login cache (${matched.source})`);
      return matched.steamId64;
    }

    // 2. Steam Web API ResolveVanityURL
    if (apiKey) {
      try {
        const url = `https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key=${encodeURIComponent(apiKey)}&vanityurl=${encodeURIComponent(clean)}`;
        const res = await this.httpGetJson(url);
        if (res && res.response && res.response.success === 1 && res.response.steamid) {
          return res.response.steamid;
        }
      } catch (err) {
        console.warn('[VaporFetch] ResolveVanityURL error:', err.message);
      }
    }

    // 3. Steam Community XML lookup
    try {
      const url = `https://steamcommunity.com/id/${encodeURIComponent(clean)}/?xml=1`;
      const xml = await this.httpGetText(url);
      const match = xml.match(/<steamID64>(\d{17})<\/steamID64>/i);
      if (match) {
        return match[1];
      }
    } catch (err) {
      console.warn('[VaporFetch] Community XML lookup error:', err.message);
    }

    return null;
  }

  /**
   * Sync games from Steam Community profile or Steam Web API
   */
  async syncSteamLibrary(identifier, apiKey) {
    let clean = String(identifier || '').trim();
    if (!clean) {
      throw new Error('Steam username, vanity URL, or SteamID64 is required');
    }

    clean = clean.replace(/^https?:\/\/steamcommunity\.com\/(id|profiles)\//i, '').replace(/\/.*$/, '').trim();

    let steamId64 = /^\d{17}$/.test(clean) ? clean : null;
    let games = [];
    const errors = [];

    // Step 1: Resolve vanity URL if needed
    if (!steamId64) {
      steamId64 = await this.resolveToSteamId64(clean, apiKey);
    }

    // Step 2: Fetch via Web API if API key is provided
    if (apiKey) {
      if (!steamId64) {
        errors.push(`Could not resolve username/vanity "${clean}" to a numeric SteamID64. Try entering your 17-digit SteamID64 directly.`);
      } else {
        try {
          games = await this.fetchViaWebApi(steamId64, apiKey);
        } catch (err) {
          errors.push(`Web API: ${err.message}`);
        }
      }
    }

    // Step 3: Try Community HTML embed (var rgGames = [...])
    if (!games || games.length === 0) {
      try {
        const idToTry = steamId64 || clean;
        const htmlGames = await this.fetchViaCommunityHtml(idToTry);
        if (htmlGames && htmlGames.length > 0) {
          games = htmlGames;
        }
      } catch (err) {
        errors.push(`Community HTML: ${err.message}`);
      }
    }

    // Step 4: Fallback to Steam Community XML
    if (!games || games.length === 0) {
      try {
        const idToTry = steamId64 || clean;
        const xmlGames = await this.fetchViaCommunityXml(idToTry);
        if (xmlGames && xmlGames.length > 0) {
          games = xmlGames;
        }
      } catch (err) {
        errors.push(`Community XML: ${err.message}`);
      }
    }

    // If still no games, provide clear instructions
    if (!games || games.length === 0) {
      const details = errors.length > 0 ? `\n\nDetails:\n${errors.join('\n')}` : '';
      throw new Error(
        `Could not retrieve games for "${clean}".${details}\n\n` +
        `Troubleshooting:\n` +
        `1. Steam Privacy Settings: In your Steam Profile -> Edit Profile -> Privacy Settings -> Set "Game details" to "Public" and uncheck "Always keep my total playtime private".\n` +
        `2. Use your 17-digit numeric SteamID64 (from Steam -> Account details, or steamid.io) rather than your login name.\n` +
        `3. Or use the "Batch AppID Import" tab to paste your AppIDs directly!`
      );
    }

    let addedCount = 0;
    for (const g of games) {
      if (!this.userGames.some(existing => existing.appId === g.appId)) {
        this.userGames.push(g);
        addedCount++;
      }
    }

    this.saveUserLibrary();

    return {
      success: true,
      totalImported: games.length,
      newlyAdded: addedCount,
      steamId64: steamId64 || clean,
      games: this.getLibrary()
    };
  }

  /**
   * Sync games using SteamCMD +licenses_print
   * Directly authenticates with Valve's Steam servers—bypasses profile privacy and API key requirements!
   * @param {string} username
   * @param {string} [password]
   * @param {string} [steamGuardCode]
   */
  async syncViaSteamCmd(username, password, steamGuardCode) {
    const user = (username || process.env.STEAM_USERNAME || '').trim();
    if (!user) {
      throw new Error('Steam username is required for SteamCMD license sync.');
    }

    const pass = password || process.env.STEAM_PASSWORD || '';
    const guard = (steamGuardCode || '').trim();
    const args = [];

    if (pass && guard) {
      args.push('+login', user, pass, guard);
    } else if (pass) {
      args.push('+login', user, pass);
    } else {
      args.push('+login', user);
    }

    args.push('+licenses_print', '+quit');

    return new Promise((resolve, reject) => {
      let output = '';
      let procExited = false;

      const proc = spawn(this.steamCmdPath, args, {
        env: {
          ...process.env,
          HOME: this.configDir,
          LC_ALL: 'C'
        },
        stdio: ['pipe', 'pipe', 'pipe']
      });

      // 45s timeout for SteamCMD command
      const timer = setTimeout(() => {
        if (!procExited) {
          try { proc.kill('SIGKILL'); } catch (e) {}
          reject(new Error('SteamCMD license sync timed out after 45 seconds. Check network connection or verify credentials.'));
        }
      }, 45000);

      proc.stdout.on('data', chunk => output += chunk.toString());
      proc.stderr.on('data', chunk => output += chunk.toString());

      proc.on('close', async (code) => {
        procExited = true;
        clearTimeout(timer);

        // 1. Detect 2FA Steam Guard Required (Codes 63, 65, or explicit prompts)
        if (/result code 63/i.test(output) || /NeedTwoFactorCode/i.test(output) || /result code 65/i.test(output) || /Steam Guard code/i.test(output) || /Two-factor code/i.test(output) || /Account Logon Denied/i.test(output)) {
          return reject(new Error('Steam Guard 2FA is required! Please enter the 5-character code from your Steam Mobile Authenticator app or Email in the "Steam Guard Code" field below and click "Sync via SteamCMD".'));
        }

        // 2. Detect 2FA Code Mismatch (Code 87)
        if (/result code 87/i.test(output) || /TwoFactorCodeMismatch/i.test(output)) {
          return reject(new Error('Invalid Steam Guard 2FA code. Please check the code in your Steam Mobile App or Email and try again.'));
        }

        // 3. Detect Invalid Credentials (Code 5)
        if (/result code 5/i.test(output) || /Invalid Password/i.test(output) || /Login Failure/i.test(output)) {
          return reject(new Error('Steam login failure: Invalid username or password. Please verify your credentials.'));
        }

        // 4. Detect Rate Limiting (Code 84)
        if (/result code 84/i.test(output) || /Rate Limit Exceeded/i.test(output)) {
          return reject(new Error('Steam rate limit reached. Valve is temporarily throttling requests. Please wait 2-3 minutes before retrying.'));
        }

        // Parse AppIDs and optional titles from licenses_print output
        const foundApps = new Map();
        const regexDetailed = /-\s*AppID\s*(\d+)\s*:\s*"?([^"\r\n]+)"?/gi;
        let match;
        while ((match = regexDetailed.exec(output)) !== null) {
          const id = match[1];
          const name = match[2].trim().replace(/^_+|_+$/g, '');
          if (parseInt(id, 10) > 10) {
            foundApps.set(id, name);
          }
        }

        const regexSimple = /AppID\s*[:\s]\s*(\d+)/gi;
        while ((match = regexSimple.exec(output)) !== null) {
          const id = match[1];
          if (parseInt(id, 10) > 10 && !foundApps.has(id)) {
            foundApps.set(id, null);
          }
        }

        if (foundApps.size === 0) {
          const cleanSnippet = (output || '')
            .replace(new RegExp(pass || '_____', 'g'), '***')
            .split('\n')
            .map(l => l.trim())
            .filter(l => l && !l.includes('Redirecting stderr'))
            .slice(-3)
            .join(' | ');
          return reject(new Error(`No licenses found. SteamCMD status: "${cleanSnippet || 'Process exited without output'}". Enter your 5-digit Steam Guard code or check credentials.`));
        }

        let addedCount = 0;
        const appEntries = Array.from(foundApps.entries());

        for (const [appId, gameName] of appEntries) {
          if (!this.userGames.some(g => g.appId === appId)) {
            let name = gameName;
            let headerImage = `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${appId}/header.jpg`;

            if (!name) {
              try {
                const info = await getAppInfo(appId);
                name = info.name || `App ${appId}`;
                headerImage = info.headerImage || headerImage;
              } catch (e) {
                name = `App ${appId}`;
              }
            }

            const dir = (name || appId).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');

            this.userGames.push({
              appId,
              name,
              dir,
              type: 'game',
              platform: 'windows',
              anonymous: false,
              headerImage
            });
            addedCount++;
          }
        }

        this.saveUserLibrary();

        resolve({
          success: true,
          totalImported: foundApps.size,
          newlyAdded: addedCount,
          games: this.getLibrary()
        });
      });

      proc.on('error', (err) => {
        procExited = true;
        clearTimeout(timer);
        reject(new Error(`Failed to execute steamcmd: ${err.message}`));
      });
    });
  }

  fetchViaCommunityHtml(identifier) {
    return new Promise((resolve) => {
      const isSteamId64 = /^\d{17}$/.test(identifier);
      const urlPath = isSteamId64 ? `/profiles/${identifier}/games/?tab=all` : `/id/${identifier}/games/?tab=all`;
      const url = `https://steamcommunity.com${urlPath}`;

      this.httpGetText(url).then(html => {
        const match = html.match(/var\s+rgGames\s*=\s*(\[[\s\S]*?\]);/i);
        if (match) {
          try {
            const parsed = JSON.parse(match[1]);
            if (Array.isArray(parsed) && parsed.length > 0) {
              const list = parsed.map(g => ({
                appId: String(g.appid),
                name: g.name || `App ${g.appid}`,
                dir: (g.name || String(g.appid)).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, ''),
                type: 'game',
                platform: 'windows',
                anonymous: false,
                headerImage: `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${g.appid}/header.jpg`
              }));
              return resolve(list);
            }
          } catch (e) {}
        }
        resolve([]);
      }).catch(() => resolve([]));
    });
  }

  fetchViaCommunityXml(identifier) {
    return new Promise((resolve) => {
      const isSteamId64 = /^\d{17}$/.test(identifier);
      const urlPath = isSteamId64 ? `/profiles/${identifier}/games?tab=all&xml=1` : `/id/${identifier}/games?tab=all&xml=1`;
      const url = `https://steamcommunity.com${urlPath}`;

      this.httpGetText(url).then(xml => {
        resolve(this.parseGamesXml(xml));
      }).catch(() => resolve([]));
    });
  }

  parseGamesXml(xmlText) {
    const games = [];
    const gameBlocks = xmlText.match(/<game>[\s\S]*?<\/game>/gi) || [];

    for (const block of gameBlocks) {
      const idMatch = block.match(/<appID>(\d+)<\/appID>/i);
      const nameMatch = block.match(/<name><!\[CDATA\[([\s\S]*?)\]\]><\/name>/i) || block.match(/<name>(.*?)<\/name>/i);

      if (idMatch && nameMatch) {
        const appId = idMatch[1].trim();
        const name = nameMatch[1].trim();
        const dir = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');

        games.push({
          appId,
          name,
          dir,
          type: 'game',
          platform: 'windows',
          anonymous: false,
          headerImage: `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${appId}/header.jpg`
        });
      }
    }
    return games;
  }

  fetchViaWebApi(steamId64, apiKey) {
    return new Promise((resolve, reject) => {
      const url = `https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key=${encodeURIComponent(apiKey)}&steamid=${encodeURIComponent(steamId64)}&include_appinfo=1&include_played_free_games=1&format=json`;

      https.get(url, { headers: { 'User-Agent': 'VaporFetch/1.0' }, timeout: 15000 }, (res) => {
        if (res.statusCode === 403) {
          return reject(new Error('HTTP 403 Forbidden: Invalid Steam Web API Key. Check your key at steamcommunity.com/dev/apikey'));
        }
        if (res.statusCode === 400) {
          return reject(new Error('HTTP 400 Bad Request: Invalid SteamID parameter. Must be a 17-digit SteamID64 (e.g. 76561198...).'));
        }
        if (res.statusCode !== 200) {
          return reject(new Error(`HTTP ${res.statusCode} from Steam Web API.`));
        }

        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const parsed = JSON.parse(data);
            if (parsed.response) {
              if (Array.isArray(parsed.response.games) && parsed.response.games.length > 0) {
                const list = parsed.response.games.map(g => ({
                  appId: String(g.appid),
                  name: g.name || `App ${g.appid}`,
                  dir: (g.name || String(g.appid)).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, ''),
                  type: 'game',
                  platform: 'windows',
                  anonymous: false,
                  headerImage: `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${g.appid}/header.jpg`
                }));
                return resolve(list);
              } else {
                return reject(new Error(
                  'Steam Web API returned an empty game list (0 games found).\n\n' +
                  'Why this happens:\n' +
                  'Valve sets "Game details" to Private by default on all Steam profiles!\n\n' +
                  'How to fix it in 15 seconds:\n' +
                  '1. In Steam, go to your Profile -> Edit Profile -> Privacy Settings\n' +
                  '2. Set "Game details" to "Public"\n' +
                  '3. Uncheck "Always keep my total playtime private"\n\n' +
                  'Tip: If you prefer to keep your profile private, use the "Batch AppID Import" tab or "SteamCMD Account Sync" tab instead!'
                ));
              }
            }
            reject(new Error('Invalid response structure from Steam Web API.'));
          } catch (e) {
            reject(new Error(`Failed to parse Steam API response: ${e.message}`));
          }
        });
      }).on('error', (err) => reject(new Error(`Network error contacting Steam API: ${err.message}`)));
    });
  }

  httpGetJson(url) {
    return new Promise((resolve, reject) => {
      https.get(url, { headers: { 'User-Agent': 'VaporFetch/1.0' }, timeout: 10000 }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            reject(e);
          }
        });
      }).on('error', reject);
    });
  }

  httpGetText(url) {
    return new Promise((resolve, reject) => {
      const options = {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 VaporFetch/1.0'
        },
        timeout: 10000
      };
      https.get(url, options, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          https.get(res.headers.location, options, (redirRes) => {
            let data = '';
            redirRes.on('data', chunk => data += chunk);
            redirRes.on('end', () => resolve(data));
          }).on('error', reject);
          return;
        }
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => resolve(data));
      }).on('error', reject);
    });
  }
}

module.exports = LibraryManager;
