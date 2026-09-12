const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');

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
    // Merge catalog and userGames by appId
    const map = new Map();

    // Default catalog first
    for (const item of DEFAULT_CATALOG) {
      map.set(item.appId, {
        ...item,
        headerImage: `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${item.appId}/header.jpg`,
        isUserOwned: false
      });
    }

    // User games overwrite/add
    for (const item of this.userGames) {
      map.set(item.appId, {
        ...item,
        headerImage: item.headerImage || `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${item.appId}/header.jpg`,
        isUserOwned: true
      });
    }

    // Inspect downloads directory to detect which games are already installed on NAS
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
      dir: game.dir || game.name.toLowerCase().replace(/[^a-z0-9]+/g, '_'),
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
   * Sync games from Steam Community profile or Steam Web API
   * @param {string} identifier - Steam Username, Custom Vanity URL, or SteamID64
   * @param {string} [apiKey] - Optional Steam Web API Key
   */
  async syncSteamLibrary(identifier, apiKey) {
    const cleanId = String(identifier || '').trim();
    if (!cleanId) {
      throw new Error('Steam username, vanity URL, or SteamID64 is required');
    }

    let games = [];

    // Method 1: If API key and 64-bit Steam ID provided, use official Steam Web API
    if (apiKey && /^\d{17}$/.test(cleanId)) {
      games = await this.fetchViaWebApi(cleanId, apiKey);
    }

    // Method 2: If no games yet, attempt public Steam Community games XML
    if (!games || games.length === 0) {
      games = await this.fetchViaCommunityXml(cleanId);
    }

    if (!games || games.length === 0) {
      throw new Error(`Could not find public games for "${cleanId}". Make sure your Steam profile and game details are set to "Public", or provide a Steam Web API Key.`);
    }

    // Merge discovered games into userGames
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
      games: this.getLibrary()
    };
  }

  fetchViaCommunityXml(identifier) {
    return new Promise((resolve) => {
      const isSteamId64 = /^\d{17}$/.test(identifier);
      const urlPath = isSteamId64 ? `/profiles/${identifier}/games?tab=all&xml=1` : `/id/${identifier}/games?tab=all&xml=1`;
      const url = `https://steamcommunity.com${urlPath}`;

      const options = {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 VaporFetch/1.0'
        },
        timeout: 10000
      };

      https.get(url, options, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          // Handle redirect
          https.get(res.headers.location, options, (redirRes) => {
            let data = '';
            redirRes.on('data', chunk => data += chunk);
            redirRes.on('end', () => resolve(this.parseGamesXml(data)));
          }).on('error', () => resolve([]));
          return;
        }

        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => resolve(this.parseGamesXml(data)));
      }).on('error', () => resolve([]));
    });
  }

  parseGamesXml(xmlText) {
    const games = [];
    // Regex extract <game><appID>...</appID><name><![CDATA[...]]></name>
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
    return new Promise((resolve) => {
      const url = `https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key=${encodeURIComponent(apiKey)}&steamid=${encodeURIComponent(steamId64)}&include_appinfo=1&format=json`;

      https.get(url, { timeout: 10000 }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const parsed = JSON.parse(data);
            if (parsed.response && Array.isArray(parsed.response.games)) {
              const list = parsed.response.games.map(g => ({
                appId: String(g.appid),
                name: g.name,
                dir: g.name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, ''),
                type: 'game',
                platform: 'windows',
                anonymous: false,
                headerImage: `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${g.appid}/header.jpg`
              }));
              return resolve(list);
            }
          } catch (e) {}
          resolve([]);
        });
      }).on('error', () => resolve([]));
    });
  }
}

module.exports = LibraryManager;

