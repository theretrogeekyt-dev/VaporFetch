const assert = require('assert');
const path = require('path');
const fs = require('fs');
const Downloader = require('../src/downloader');

async function testPostProcessing() {
  console.log('--- Testing Post-Download Destination Cleanup ---');

  const testDir = path.join(__dirname, 'temp_postprocess_test');
  if (fs.existsSync(testDir)) fs.rmSync(testDir, { recursive: true, force: true });
  fs.mkdirSync(testDir, { recursive: true });

  const downloader = new Downloader({
    downloadsDir: testDir,
    configDir: path.join(__dirname, 'temp_config')
  });

  // Mock test game directory
  const gameDir = path.join(testDir, 'doom');
  fs.mkdirSync(gameDir, { recursive: true });

  // 1. Create fake game file
  fs.writeFileSync(path.join(gameDir, 'doom.exe'), 'binary_data');

  // 2. Create fake steamapps folder with manifest and downloading cache
  const steamAppsDir = path.join(gameDir, 'steamapps');
  fs.mkdirSync(path.join(steamAppsDir, 'downloading'), { recursive: true });
  fs.writeFileSync(path.join(steamAppsDir, 'appmanifest_2280.acf'), 'AppState { ... }');

  // 3. Create fake _CommonRedist folder with vcredist
  const redistDir = path.join(gameDir, '_CommonRedist');
  fs.mkdirSync(path.join(redistDir, 'vcredist'), { recursive: true });
  fs.writeFileSync(path.join(redistDir, 'vcredist', 'vcredist_x64.exe'), 'redist_binary');

  assert(fs.existsSync(steamAppsDir), 'steamapps should exist before cleanup');
  assert(fs.existsSync(redistDir), '_CommonRedist should exist before cleanup');

  // Run postProcessDestination
  downloader.postProcessDestination(gameDir, {
    removeSteamApps: true,
    renameRedist: true
  });

  // Verification 1: steamapps folder should be completely gone
  assert(!fs.existsSync(steamAppsDir), 'steamapps folder should be removed');

  // Verification 2: _CommonRedist should be renamed to dependencies
  assert(!fs.existsSync(redistDir), '_CommonRedist should no longer exist');
  const dependenciesDir = path.join(gameDir, 'dependencies');
  assert(fs.existsSync(dependenciesDir), 'dependencies folder should now exist');
  assert(fs.existsSync(path.join(dependenciesDir, 'vcredist', 'vcredist_x64.exe')), 'Dependencies content should be preserved');

  // Verification 3: Game file should still be untouched
  assert(fs.existsSync(path.join(gameDir, 'doom.exe')), 'doom.exe should remain untouched');

  console.log('✔ Direct steamapps removal and _CommonRedist rename to dependencies passed!');

  // Test Case B: redist folder in subfolder or named "redist"
  const gameDir2 = path.join(testDir, 'game2');
  fs.mkdirSync(path.join(gameDir2, 'redist'), { recursive: true });
  fs.writeFileSync(path.join(gameDir2, 'redist', 'directx.exe'), 'dx_data');

  downloader.postProcessDestination(gameDir2, {
    removeSteamApps: true,
    renameRedist: true
  });

  assert(!fs.existsSync(path.join(gameDir2, 'redist')), 'redist should be gone');
  assert(fs.existsSync(path.join(gameDir2, 'dependencies', 'directx.exe')), 'dependencies/directx.exe should exist');
  console.log('✔ "redist" variant folder renaming passed!');

  // Cleanup
  fs.rmSync(testDir, { recursive: true, force: true });
  console.log('\nAll post-processing cleanup tests passed successfully!');
}

testPostProcessing().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});

