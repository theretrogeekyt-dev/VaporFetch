const https = require('https');

// Curated popular presets for dedicated servers and games
const PRESETS = [
  { appId: '2394010', name: 'Palworld Dedicated Server', dir: 'palworld', anonymous: true, platform: 'windows' },
  { appId: '730', name: 'Counter-Strike 2 Dedicated Server', dir: 'cs2', anonymous: true, platform: 'linux' },
  { appId: '896660', name: 'Valheim Dedicated Server', dir: 'valheim', anonymous: true, platform: 'linux' },
  { appId: '2278520', name: 'Enshrouded Dedicated Server', dir: 'enshrouded', anonymous: true, platform: 'windows' },
  { appId: '258550', name: 'Rust Dedicated Server', dir: 'rust', anonymous: true, platform: 'linux' },
  { appId: '2430930', name: 'Ark: Survival Ascended Dedicated Server', dir: 'ark_sa', anonymous: true, platform: 'windows' },
  { appId: '380870', name: 'Project Zomboid Dedicated Server', dir: 'zomboid', anonymous: true, platform: 'linux' },
  { appId: '2465200', name: 'Sons of the Forest Dedicated Server', dir: 'sotf', anonymous: true, platform: 'windows' },
  { appId: '294420', name: '7 Days to Die Dedicated Server', dir: '7daystodie', anonymous: true, platform: 'linux' },
  { appId: '4020', name: "Garry's Mod Dedicated Server", dir: 'gmod', anonymous: true, platform: 'linux' },
  { appId: '232250', name: 'Team Fortress 2 Dedicated Server', dir: 'tf2', anonymous: true, platform: 'linux' },
  { appId: '222860', name: 'Left 4 Dead 2 Dedicated Server', dir: 'l4d2', anonymous: true, platform: 'linux' },
  { appId: '1690800', name: 'Satisfactory Dedicated Server', dir: 'satisfactory', anonymous: true, platform: 'linux' },
  { appId: '1829350', name: 'V Rising Dedicated Server', dir: 'vrising', anonymous: true, platform: 'windows' },
  { appId: '105600', name: 'Terraria Dedicated Server', dir: 'terraria', anonymous: true, platform: 'windows' }
];

/**
 * Fetch game details from the official public Steam Store API.
 * Gracefully handles rate-limiting, non-existent apps, and tools not listed on the store.
 * @param {string|number} appId
 * @returns {Promise<Object>}
 */
function getAppInfo(appId) {
  return new Promise((resolve) => {
    const id = String(appId).trim();
    if (!id || !/^\d+$/.test(id)) {
      return resolve({
        success: false,
        error: 'Invalid AppID format'
      });
    }

    // Check presets first for quick response
    const preset = PRESETS.find(p => p.appId === id);

    const url = `https://store.steampowered.com/api/appdetails?appids=${id}`;
    const req = https.get(url, { headers: { 'User-Agent': 'VaporFetch/1.0' } }, (res) => {
      let rawData = '';
      res.on('data', chunk => rawData += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(rawData);
          if (parsed[id] && parsed[id].success && parsed[id].data) {
            const data = parsed[id].data;
            return resolve({
              success: true,
              appId: id,
              name: data.name,
              headerImage: data.header_image || `https://cdn.cloudflare.steamstatic.com/steam/apps/${id}/header.jpg`,
              isFree: data.is_free || false,
              type: data.type || 'game',
              developers: data.developers || [],
              presetMatch: preset || null
            });
          }
        } catch (e) {
          // JSON parse failed or non-200 response
        }

        // Fallback to preset or standard Akamai CDN banner image
        resolve({
          success: true,
          appId: id,
          name: preset ? preset.name : `Steam App ${id}`,
          headerImage: `https://cdn.cloudflare.steamstatic.com/steam/apps/${id}/header.jpg`,
          isFree: preset ? preset.anonymous : false,
          type: preset ? 'server' : 'unknown',
          developers: [],
          presetMatch: preset || null
        });
      });
    });

    req.on('error', () => {
      resolve({
        success: true,
        appId: id,
        name: preset ? preset.name : `Steam App ${id}`,
        headerImage: `https://cdn.cloudflare.steamstatic.com/steam/apps/${id}/header.jpg`,
        isFree: preset ? preset.anonymous : false,
        type: preset ? 'server' : 'unknown',
        presetMatch: preset || null
      });
    });

    req.setTimeout(5000, () => {
      req.abort();
      resolve({
        success: true,
        appId: id,
        name: preset ? preset.name : `Steam App ${id}`,
        headerImage: `https://cdn.cloudflare.steamstatic.com/steam/apps/${id}/header.jpg`,
        isFree: preset ? preset.anonymous : false,
        type: preset ? 'server' : 'unknown',
        presetMatch: preset || null
      });
    });
  });
}

function getPresets() {
  return PRESETS;
}

module.exports = {
  getAppInfo,
  getPresets
};

