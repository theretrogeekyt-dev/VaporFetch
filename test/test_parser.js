// Test SteamCMD output parser logic and helper functions

function formatBytes(bytes, decimals = 2) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

const progressRegex = /Update state \((0x[0-9a-fA-F]+)\)\s*:\s*([^,]+),\s*progress:\s*([0-9.]+)\s*\(([0-9]+)\s*\/\s*([0-9]+)\)/i;

function parseLine(line) {
  if (/steam guard code:/i.test(line) || /two-factor code:/i.test(line)) {
    return { type: 'steamguard_required' };
  }

  const match = line.match(progressRegex);
  if (match) {
    return {
      type: 'progress',
      stateCode: match[1],
      stage: match[2].trim(),
      percent: parseFloat(match[3]),
      bytesCurrent: parseInt(match[4], 10),
      bytesTotal: parseInt(match[5], 10)
    };
  }

  if (/success!\s+app\s+['"]?(\d+)['"]?\s+fully installed/i.test(line)) {
    const appMatch = line.match(/success!\s+app\s+['"]?(\d+)['"]?\s+fully installed/i);
    return { type: 'success', appId: appMatch[1] };
  }

  if (/error!\s+failed to install app.*\(no subscription\)/i.test(line)) {
    return { type: 'error', code: 'NO_SUBSCRIPTION' };
  }

  if (/disk write failure/i.test(line)) {
    return { type: 'error', code: 'DISK_WRITE_FAILURE' };
  }

  return { type: 'log', text: line };
}

// Test cases
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

// 1. Test Progress Regex with downloading
const line1 = 'Update state (0x61) : Downloading, progress: 42.50 (3446865920 / 8111222200)';
const res1 = parseLine(line1);
assert(res1.type === 'progress', 'Line 1 type should be progress');
assert(res1.stage === 'Downloading', 'Line 1 stage should be Downloading');
assert(res1.percent === 42.5, 'Line 1 percent should be 42.5');
assert(res1.bytesCurrent === 3446865920, 'Line 1 bytesCurrent mismatch');
assert(res1.bytesTotal === 8111222200, 'Line 1 bytesTotal mismatch');

// 2. Test Preallocating
const line2 = 'Update state (0x5) : Preallocating, progress: 10.00 (1000 / 10000)';
const res2 = parseLine(line2);
assert(res2.type === 'progress', 'Line 2 type should be progress');
assert(res2.stage === 'Preallocating', 'Line 2 stage should be Preallocating');

// 3. Test Validating
const line3 = 'Update state (0x11) : Validating, progress: 99.85 (800000 / 801000)';
const res3 = parseLine(line3);
assert(res3.type === 'progress', 'Line 3 type should be progress');
assert(res3.stage === 'Validating', 'Line 3 stage should be Validating');

// 4. Test Steam Guard prompts
const line4a = 'Logging in user \'retro\' to Steam Public...\nSteam Guard code:';
assert(parseLine(line4a).type === 'steamguard_required', 'Line 4a should detect Steam Guard');
const line4b = 'Two-factor code: ';
assert(parseLine(line4b).type === 'steamguard_required', 'Line 4b should detect Two-factor code');

// 5. Test Success
const line5 = "Success! App '2394010' fully installed.";
const res5 = parseLine(line5);
assert(res5.type === 'success', 'Line 5 should be success');
assert(res5.appId === '2394010', 'Line 5 appId should be 2394010');

// 6. Test Errors
const line6 = "ERROR! Failed to install app '730' (No subscription)";
assert(parseLine(line6).type === 'error' && parseLine(line6).code === 'NO_SUBSCRIPTION', 'Line 6 should be NO_SUBSCRIPTION');

const line7 = "ERROR! App '730' state is 0x606 after update job : Disk write failure";
assert(parseLine(line7).type === 'error' && parseLine(line7).code === 'DISK_WRITE_FAILURE', 'Line 7 should be DISK_WRITE_FAILURE');

// 7. Test formatBytes
assert(formatBytes(0) === '0 B', '0 bytes should format to 0 B');
assert(formatBytes(1024) === '1 KB', '1024 bytes should format to 1 KB');
assert(formatBytes(1048576) === '1 MB', '1048576 bytes should format to 1 MB');
assert(formatBytes(1073741824) === '1 GB', '1073741824 bytes should format to 1 GB');

print('Parser and formatter tests completed: ' + testsPassed + ' passed, ' + testsFailed + ' failed.');
if (testsFailed > 0) {
  throw new Error('Some tests failed!');
}

