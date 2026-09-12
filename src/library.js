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
   * Resolve vanity URL or profile link to a numeric 64-bit Steam ID
   */
  async resolveToSteamId64(identifier, apiKey) {
    let clean = String(identifier || '').trim();
    clean = clean.replace(/^https?:\/\/steamcommunity\.com\/(id|profiles)\//i, '').replace(/\/.*$/, '').trim();

    if (/^\d{17}$/.test(clean)) {
      return clean;
    }

    // 1. Steam Web API ResolveVanityURL
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

    // 2. Steam Community XML lookup
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
   * @param {string} identifier - Steam Username, Custom Vanity URL, or SteamID64
   * @param {string} [apiKey] - Optional Steam Web API Key
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
        errors.push(`Could not resolve vanity URL "${clean}" to a 64-bit Steam ID. Check username or enter your 17-digit SteamID64 directly.`);
      } else {
        try {
          games = await this.fetchViaWebApi(steamId64, apiKey);
        } catch (err) {
          errors.push(`Web API error: ${err.message}`);
        }
      }
    }

    // Step 3: Fallback to Steam Community games XML (no API key needed)
    if (!games || games.length === 0) {
      try {
        const idToTry = steamId64 || clean;
        const xmlGames = await this.fetchViaCommunityXml(idToTry);
        if (xmlGames && xmlGames.length > 0) {
          games = xmlGames;
        }
      } catch (err) {
        errors.push(`Community XML error: ${err.message}`);
      }
    }

    // If still no games, provide clear instructions
    if (!games || games.length === 0) {
      const details = errors.length > 0 ? `\nDetails: ${errors.join('\n')}` : '';
      throw new Error(
        `Failed to retrieve games for "${clean}".${details}\n\n` +
        `Troubleshooting:\n` +
        `1. If using an API key, enter your 17-digit SteamID64 (from your Steam account details or steamid.io).\n` +
        `2. Ensure your Steam Privacy Settings are set to Public: In Steam, go to Profile -> Edit Profile -> Privacy Settings -> Set "Game details" to "Public" and uncheck "Always keep my total playtime private".\n` +
        `3. Or use "Sync via SteamCMD" to fetch owned licenses directly with your Steam login.`
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
   */
  async syncViaSteamCmd(username, password) {
    const user = (username || process.env.STEAM_USERNAME || '').trim();
    if (!user) {
      throw new Error('Steam username is required for SteamCMD license sync.');
    }

    const pass = password || process.env.STEAM_PASSWORD || '';
    const args = [];

    if (pass) {
      args.push('+login', user, pass);
    } else {
      args.push('+login', user);
    }

    args.push('+licenses_print', '+quit');

    return new Promise((resolve, reject) => {
      let output = '';
      let isError = false;

      const proc = spawn(this.steamCmdPath, args, {
        env: {
          ...process.env,
          HOME: this.configDir,
          LC_ALL: 'C'
        }
      });

      proc.stdout.on('data', chunk => output += chunk.toString());
      proc.stderr.on('data', chunk => output += chunk.toString());

      proc.on('close', async (code) => {
        if (/Steam Guard code:/i.test(output) || /Two-factor code:/i.test(output)) {
          return reject(new Error('Steam Guard 2FA is required. Please login once via a download task to cache your Steam Guard token, then retry.'));
        }

        if (/Invalid Password/i.test(output) || /Login Failure/i.test(output)) {
          return reject(new Error('Steam login failure: Invalid username or password.'));
        }

        // Parse AppIDs from licenses_print output
        // Patterns in SteamCMD: "License packageID 12345: AppID 2280 (DOOM + DOOM II)" or "- Package 123: AppID 2280"
        const foundAppIds = new Set();
        const appMatches = output.matchAll(/AppID\s*[:\s](\d+)(?:\s*\(([^)]+)\))?/gi);

        for (const m of appMatches) {
          const appId = m[1];
          // Filter out internal tools / runtime IDs
          if (parseInt(appId, 10) > 10) {
            foundAppIds.add(appId);
          }
        }

        if (foundAppIds.size === 0) {
          return reject(new Error('No licenses found in SteamCMD output. Make sure the account owns games.'));
        }

        let addedCount = 0;
        const appList = Array.from(foundAppIds);

        // Batch inspect up to 50 games for names
        for (const appId of appList.slice(0, 50)) {
          if (!this.userGames.some(g => g.appId === appId)) {
            const info = await getAppInfo(appId);
            this.userGames.push({
              appId,
              name: info.name || `App ${appId}`,
              dir: (info.name || appId).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, ''),
              type: 'game',
              platform: 'windows',
              anonymous: false,
              headerImage: info.headerImage || `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${appId}/header.jpg`
            });
            addedCount++;
          }
        }

        this.saveUserLibrary();

        resolve({
          success: true,
          totalImported: foundAppIds.size,
          newlyAdded: addedCount,
          games: this.getLibrary()
        });
      });

      proc.on('error', (err) => reject(new Error(`Failed to execute steamcmd: ${err.message}`)));
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
          return reject(new Error('HTTP 403 Forbidden: Invalid Steam Web API Key.'));
        }
        if (res.statusCode === 400) {
          return reject(new Error('HTTP 400 Bad Request: Invalid SteamID parameter.'));
        }
        if (res.statusCode !== 200) {
          return reject(new Error(`HTTP ${res.statusCode} from Steam API.`));
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
                return reject(new Error('Steam returned an empty game list. In Steam Privacy Settings, please verify "Game details" is set to "Public" and uncheck "Always keep playtime private".'));
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
