const fs = require('fs');
const path = require('path');

function formatBytes(bytes, decimals = 2) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

/**
 * Get filesystem capacity and free space on the target downloads directory
 * @param {string} targetDir
 * @returns {Promise<Object>}
 */
async function getStorageInfo(targetDir) {
  try {
    if (!fs.existsSync(targetDir)) {
      fs.mkdirSync(targetDir, { recursive: true });
    }

    if (fs.promises.statfs) {
      const stats = await fs.promises.statfs(targetDir);
      const totalBytes = stats.blocks * stats.bsize;
      const freeBytes = stats.bfree * stats.bsize;
      const availableBytes = stats.bavail * stats.bsize;
      const usedBytes = totalBytes - freeBytes;
      const percentUsed = totalBytes > 0 ? ((usedBytes / totalBytes) * 100).toFixed(1) : 0;

      return {
        path: targetDir,
        totalBytes,
        freeBytes: availableBytes,
        usedBytes,
        totalFormatted: formatBytes(totalBytes),
        freeFormatted: formatBytes(availableBytes),
        usedFormatted: formatBytes(usedBytes),
        percentUsed: Number(percentUsed),
        writable: checkWritableSync(targetDir)
      };
    }
  } catch (err) {
    // If statfs fails (e.g. some virtual filesystems), return basic status
  }

  return {
    path: targetDir,
    totalBytes: null,
    freeBytes: null,
    usedBytes: null,
    totalFormatted: 'Unknown',
    freeFormatted: 'Unknown',
    usedFormatted: 'Unknown',
    percentUsed: 0,
    writable: checkWritableSync(targetDir)
  };
}

/**
 * Test whether the process has write permissions on the directory
 * @param {string} targetDir
 * @returns {boolean}
 */
function checkWritableSync(targetDir) {
  try {
    if (!fs.existsSync(targetDir)) {
      fs.mkdirSync(targetDir, { recursive: true });
    }
    const testFile = path.join(targetDir, `.vaporfetch_perm_test_${Date.now()}`);
    fs.writeFileSync(testFile, 'write_test');
    fs.unlinkSync(testFile);
    return true;
  } catch (err) {
    return false;
  }
}

/**
 * List subdirectories inside the download directory
 * @param {string} targetDir
 * @returns {Promise<string[]>}
 */
async function listSubdirectories(targetDir) {
  try {
    if (!fs.existsSync(targetDir)) {
      return [];
    }
    const entries = await fs.promises.readdir(targetDir, { withFileTypes: true });
    return entries
      .filter(entry => entry.isDirectory() && !entry.name.startsWith('.'))
      .map(entry => entry.name)
      .sort();
  } catch (err) {
    return [];
  }
}

module.exports = {
  formatBytes,
  getStorageInfo,
  checkWritableSync,
  listSubdirectories
};

