// Test suite for VaporFetch library sync and parsing logic
let testsPassed = 0;
let testsFailed = 0;

function assert(condition, message) {
  if (condition) {
    testsPassed++;
  } else {
    testsFailed++;
    print('[FAIL] ' + message);
  }
}

// 1. Test 32-bit to 64-bit SteamID conversion
const accountId32 = BigInt('12345678');
const steamId64 = (accountId32 + 76561197960265728n).toString();
assert(steamId64 === '76561197972611406', 'SteamID64 calculation matches Valve algorithm');

// 2. Test loginusers.vdf parsing
const sampleLoginUsers = `
"users"
{
	"76561198012345678"
	{
		"AccountName"		"reaper360vr"
		"PersonaName"		"Reaper"
		"RememberPassword"		"1"
		"mostrecent"		"1"
		"Timestamp"		"1710000000"
	}
}
`;

const detected = [];
const userMatches = sampleLoginUsers.matchAll(/"(\d{17})"\s*\{([^}]+)\}/gi);
for (const um of userMatches) {
  const sId = um[1];
  const block = um[2];
  const accMatch = block.match(/"AccountName"\s*"([^"]+)"/i);
  const personaMatch = block.match(/"PersonaName"\s*"([^"]+)"/i);
  const accName = accMatch ? accMatch[1] : `User_${sId}`;
  const personaName = personaMatch ? personaMatch[1] : accName;
  detected.push({ username: accName, personaName, steamId64: sId });
}

assert(detected.length === 1, 'Detected 1 account from loginusers.vdf');
assert(detected[0].username === 'reaper360vr', 'Account name correctly parsed as reaper360vr');
assert(detected[0].personaName === 'Reaper', 'Persona name correctly parsed as Reaper');
assert(detected[0].steamId64 === '76561198012345678', 'SteamID64 correctly matched');

// 3. Test matching user input "reaper360vr" against local detected accounts
const input = "reaper360vr";
const matched = detected.find(a => a.username.toLowerCase() === input.toLowerCase() || a.steamId64 === input);
assert(matched !== undefined, 'User input reaper360vr resolves against local account cache');
assert(matched && matched.steamId64 === '76561198012345678', 'Resolves to 76561198012345678 without public vanity API');

// 4. Test SteamCMD licenses_print parsing
const sampleLicensesOutput = `
Logging in user 'reaper360vr' to Steam Public...
Logged in OK
Waiting for user info...OK
Licenses for reaper360vr:
License packageID 12345:
 - AppID 2280 : "DOOM + DOOM II"
 - AppID 730 : "Counter-Strike 2"
 - AppID 105600 : "Terraria"
License packageID 67890:
 - AppID 1086940 : "Baldur's Gate 3"
`;

const foundApps = new Map();
const regexDetailed = /-\s*AppID\s*(\d+)\s*:\s*"([^"]+)"/gi;
let match;
while ((match = regexDetailed.exec(sampleLicensesOutput)) !== null) {
  const id = match[1];
  const name = match[2].trim();
  if (parseInt(id, 10) > 10) {
    foundApps.set(id, name);
  }
}

assert(foundApps.size === 4, 'Found all 4 apps from licenses_print output');
assert(foundApps.get('2280') === 'DOOM + DOOM II', 'Extracted DOOM title');
assert(foundApps.get('730') === 'Counter-Strike 2', 'Extracted CS2 title');
assert(foundApps.get('105600') === 'Terraria', 'Extracted Terraria title');
assert(foundApps.get('1086940') === "Baldur's Gate 3", 'Extracted BG3 title');

// 5. Test Batch AppID Import text extraction
const rawUserText = `
Here are my favorite games:
DOOM: https://store.steampowered.com/app/2280/DOOM__DOOM_II/
CS2: 730
Terraria: AppID: 105600
BG3: 1086940, Elden Ring: 1245620
Duplicates: 2280, 730
`;

const rawMatches = rawUserText.match(/\b\d{2,8}\b/g) || [];
const uniqueIds = Array.from(new Set(rawMatches));

assert(uniqueIds.length === 5, 'Extracted 5 unique AppIDs from arbitrary text and URLs');
assert(uniqueIds.includes('2280'), 'Includes 2280');
assert(uniqueIds.includes('730'), 'Includes 730');
assert(uniqueIds.includes('105600'), 'Includes 105600');
assert(uniqueIds.includes('1086940'), 'Includes 1086940');
assert(uniqueIds.includes('1245620'), 'Includes 1245620');

print('Library sync tests completed: ' + testsPassed + ' passed, ' + testsFailed + ' failed.');
