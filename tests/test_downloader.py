import unittest
from vaporfetch.downloader import DownloadTask, DownloadManager

class TestDownloader(unittest.TestCase):
    def test_download_task_to_dict(self):
        task = DownloadTask(appid=730, name="Counter-Strike 2", platform="windows")
        d = task.to_dict()
        self.assertEqual(d["appid"], 730)
        self.assertEqual(d["name"], "Counter-Strike 2")
        self.assertEqual(d["platform"], "windows")
        self.assertEqual(d["status"], "queued")
        self.assertEqual(d["percent"], 0.0)

    def test_queue_operations(self):
        mgr = DownloadManager()
        # Ensure clean state
        mgr.clear_queue()

        # Add single
        added = mgr.add_to_queue(400, "Portal", "linux")
        self.assertTrue(added)

        # Duplicate should be rejected
        added_dup = mgr.add_to_queue(400, "Portal", "linux")
        self.assertFalse(added_dup)

        # Add batch
        batch = [
            {"appid": 440, "name": "Team Fortress 2"},
            {"appid": 550, "name": "Left 4 Dead 2"},
            {"appid": 400, "name": "Portal"}, # Should be skipped since already queued
        ]
        count = mgr.add_batch(batch, platform="windows")
        self.assertEqual(count, 2)

        # Check queue length
        state = mgr.get_queue_state()
        self.assertEqual(len(state["queue"]), 3)

        # Remove item
        removed = mgr.remove_from_queue(440)
        self.assertTrue(removed)
        state = mgr.get_queue_state()
        self.assertEqual(len(state["queue"]), 2)

        # Clear queue
        mgr.clear_queue()
        state = mgr.get_queue_state()
        self.assertEqual(len(state["queue"]), 0)

if __name__ == "__main__":
    unittest.main()

