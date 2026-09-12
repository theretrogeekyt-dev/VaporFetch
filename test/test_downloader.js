const assert = require('assert');
const path = require('path');
const fs = require('fs');
const Downloader = require('../src/downloader');
const { formatBytes, checkWritableSync, listSubdirectories } = require('../src/disk');
const { getPresets } = require('../src/steamApi');

async function runTests() {
  console.log('--- Running VaporFetch Unit & Integration Tests ---');
  let passed = 0;

  // 1. Presets Test
  const presets = getPresets();
  assert(Array.isArray(presets) && presets.length > 0, 'Presets should return a non-empty array');
  assert(presets.some(p => p.appId === '2394010'), 'Palworld should be in presets');
  console.log('✔ Preset library verification passed');
  passed++;

  // 2. Disk Utility Tests
  const tempTestDir = path.join(__dirname, 'temp_test_nas');
  if (fs.existsSync(tempTestDir)) fs.rmSync(tempTestDir, { recursive: true, force: true });
  fs.mkdirSync(tempTestDir, { recursive: true });

  assert.strictEqual(checkWritableSync(tempTestDir), true, 'Temp dir should be writable');
  assert.strictEqual(formatBytes(1048576), '1 MB', 'formatBytes formatting check');

  fs.mkdirSync(path.join(tempTestDir, 'folder_a'));
  fs.mkdirSync(path.join(tempTestDir, 'folder_b'));
  const subdirs = await listSubdirectories(tempTestDir);
  assert.deepStrictEqual(subdirs, ['folder_a', 'folder_b'], 'listSubdirectories should list child folders');
  console.log('✔ Disk and storage utilities verification passed');
  passed++;

  // 3. Downloader Path Traversal & Validation Tests
  const testConfigDir = path.join(__dirname, 'temp_config');
  if (fs.existsSync(testConfigDir)) fs.rmSync(testConfigDir, { recursive: true, force: true });

  const downloader = new Downloader({
    downloadsDir: tempTestDir,
    configDir: testConfigDir,
    steamCmdPath: 'echo' // harmless mock command
  });

  assert.strictEqual(downloader.status, 'idle', 'Initial status should be idle');

  // Should reject invalid AppIDs
  await assert.rejects(
    async () => downloader.startDownload({ appId: 'invalid-id' }),
    /numeric Steam AppID is required/
  );
  console.log('✔ Invalid AppID rejection passed');
  passed++;

  // Should reject path traversal outside downloads directory
  await assert.rejects(
    async () => downloader.startDownload({ appId: '730', installDir: '../../etc' }),
    /Target folder path is invalid/
  );
  console.log('✔ Path traversal protection passed');
  passed++;

  // 4. Downloader Line Parsing Verification
  downloader.status = 'starting';
  downloader.currentJob = {
    appId: '730',
    appName: 'Test Game',
    installDir: path.join(tempTestDir, 'cs2'),
    progress: { percent: 0, stage: 'Init' }
  };

  downloader.parseSteamCmdLine('Update state (0x61) : Downloading, progress: 55.40 (5540000 / 10000000)');
  assert.strictEqual(downloader.status, 'downloading', 'Status should transition to downloading');
  assert.strictEqual(downloader.currentJob.progress.percent, 55.4, 'Percent should be 55.4%');
  assert.strictEqual(downloader.currentJob.progress.bytesCurrent, 5540000, 'Bytes current match');

  downloader.parseSteamCmdLine('Success! App \'730\' fully installed.');
  assert.strictEqual(downloader.status, 'completed', 'Status should transition to completed');
  assert.strictEqual(downloader.currentJob.progress.percent, 100, 'Percent should be 100%');
  console.log('✔ Downloader stdout state-machine parsing passed');
  passed++;

  // 5. Cleanup
  if (fs.existsSync(tempTestDir)) fs.rmSync(tempTestDir, { recursive: true, force: true });
  if (fs.existsSync(testConfigDir)) fs.rmSync(testConfigDir, { recursive: true, force: true });

  console.log(`\nAll ${passed} integration test suites passed successfully!`);
}

runTests().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});

