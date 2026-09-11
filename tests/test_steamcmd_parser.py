import unittest
from vaporfetch.steamcmd import (
    parse_progress_line,
    parse_licenses_output,
    check_login_output,
    RE_STEAM_GUARD,
    RE_LOGIN_SUCCESS,
    RE_LOGIN_FAIL,
    RE_APP_SUCCESS,
    RE_APP_ERROR,
)

class TestSteamCMDParser(unittest.TestCase):
    def test_parse_progress_downloading(self):
        line = "Update state (0x61) downloading, progress: 24.50 (1024000000 / 4178923520)"
        parsed = parse_progress_line(line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["state_hex"], "0x61")
        self.assertEqual(parsed["state"], "downloading")
        self.assertAlmostEqual(parsed["percent"], 24.50)
        self.assertEqual(parsed["current_bytes"], 1024000000)
        self.assertEqual(parsed["total_bytes"], 4178923520)

    def test_parse_progress_verifying(self):
        line = "Update state (0x5) verifying, progress: 99.12 (4100000000 / 4178923520)"
        parsed = parse_progress_line(line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["state"], "verifying")
        self.assertAlmostEqual(parsed["percent"], 99.12)

    def test_parse_progress_reconfiguring(self):
        line = "Update state (0x3) reconfiguring, progress: 0.00 (0 / 0)"
        parsed = parse_progress_line(line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["state"], "reconfiguring")
        self.assertEqual(parsed["current_bytes"], 0)

    def test_parse_non_progress_line(self):
        line = "Logging in user 'testuser' to Steam Public..."
        self.assertIsNone(parse_progress_line(line))

    def test_parse_licenses_output(self):
        raw_output = """
        License packageID 100123:
         - State : Active( flags 512 )
         - Purchased : Sat Jun 10 19:34:14 2017 in "US", Complimentary
         - Apps : 459860, (1 in total)
         - Depots : 459861, (1 in total)

        License packageID 166844:
         - State : Active( flags 0 )
         - Purchased : Sat Jun 2 12:43:06 2018 in "US", Wallet
         - Apps : 730, 440, (2 in total)
         - Depots : 731, 441, (2 in total)
        """
        appids = parse_licenses_output(raw_output)
        self.assertIn(459860, appids)
        self.assertIn(730, appids)
        self.assertIn(440, appids)
        self.assertEqual(len(appids), 3)

    def test_parse_licenses_output_various_formats(self):
        raw_output = """
        License packageID 10:
         - App : 730
        License packageID 20:
         - appid : 105600
        License packageID 30:
         - AppIDs: 400, 620
        License packageID 40:
         - AppID: 1086940
        """
        appids = parse_licenses_output(raw_output)
        self.assertIn(730, appids)
        self.assertIn(105600, appids)
        self.assertIn(400, appids)
        self.assertIn(620, appids)
        self.assertIn(1086940, appids)
        self.assertEqual(len(appids), 5)

    def test_2fa_detection(self):
        email_prompt = "Steam Guard code: "
        mobile_prompt = "Enter the current code from your Steam Guard Mobile Authenticator app: "
        self.assertTrue(bool(RE_STEAM_GUARD.search(email_prompt)))
        self.assertTrue(bool(RE_STEAM_GUARD.search(mobile_prompt)))

    def test_login_result_detection(self):
        from vaporfetch.steamcmd import check_login_output

        # Account Logon Denied (Email 2FA)
        r1 = check_login_output("Logging in user 'reaper360vr' to Steam Public...FAILED (Account Logon Denied)")
        self.assertIsNotNone(r1)
        self.assertEqual(r1["status"], "awaiting_2fa")
        self.assertEqual(r1["two_factor_type"], "email")

        # Need Two Factor (Mobile Authenticator 2FA)
        r2 = check_login_output("Logging in user 'reaper360vr' to Steam Public...FAILED (Account Logon Denied Need Two Factor)")
        self.assertIsNotNone(r2)
        self.assertEqual(r2["status"], "awaiting_2fa")
        self.assertEqual(r2["two_factor_type"], "mobile")

        # Result code 65
        r3 = check_login_output("FAILED with result code 65")
        self.assertIsNotNone(r3)
        self.assertEqual(r3["status"], "awaiting_2fa")

        # Result code 85
        r4 = check_login_output("FAILED with result code 85")
        self.assertIsNotNone(r4)
        self.assertEqual(r4["status"], "awaiting_2fa")
        self.assertEqual(r4["two_factor_type"], "mobile")

        # Invalid Password
        r5 = check_login_output("FAILED (Invalid Password)")
        self.assertIsNotNone(r5)
        self.assertEqual(r5["status"], "failed")
        self.assertIn("password", r5["error"].lower())

        # No Connection
        r6 = check_login_output("FAILED (No Connection)")
        self.assertIsNotNone(r6)
        self.assertEqual(r6["status"], "failed")

        # Success
        r7 = check_login_output("Logging in user 'reaper360vr' to Steam Public...Logged in OK")
        self.assertIsNotNone(r7)
        self.assertEqual(r7["status"], "logged_in")

        # 2FA prompt followed by success (latest event wins)
        r8 = check_login_output("Enter the current code from your Steam Guard Mobile Authenticator app: \nLogged in OK")
        self.assertIsNotNone(r8)
        self.assertEqual(r8["status"], "logged_in")

        # 2FA prompt followed by mismatch failure (latest event wins)
        r9 = check_login_output("Enter the current code from your Steam Guard Mobile Authenticator app: \nFAILED (Two-factor code mismatch)")
        self.assertIsNotNone(r9)
        self.assertEqual(r9["status"], "failed")

    def test_app_success_and_error(self):
        succ = "Success! App '730' fully installed."
        err = "ERROR! Failed to install app '730' (No subscription)"

        m_succ = RE_APP_SUCCESS.search(succ)
        self.assertIsNotNone(m_succ)
        self.assertEqual(m_succ.group(1), "730")

        m_err = RE_APP_ERROR.search(err)
        self.assertIsNotNone(m_err)
        self.assertEqual(m_err.group(1), "730")
        self.assertEqual(m_err.group(2), "No subscription")

    def test_start_login_with_upfront_code(self):
        from unittest.mock import patch, MagicMock
        from vaporfetch.steamcmd import start_login, auth_session

        def fake_sleep(s):
            auth_session.status = "logged_in"

        with patch("vaporfetch.steamcmd.find_steamcmd_path", return_value="/usr/local/bin/steamcmd"), \
             patch("pty.openpty", return_value=(999, 998)), \
             patch("os.close"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("threading.Thread") as mock_thread, \
             patch("time.sleep", side_effect=fake_sleep):

            mock_proc = MagicMock()
            mock_popen.return_value = mock_proc

            res = start_login("testuser", "secretpass", "R4NDM")
            self.assertEqual(auth_session.username, "testuser")
            self.assertEqual(res["status"], "logged_in")

            called_cmd = mock_popen.call_args[0][0]
            self.assertIn("+login", called_cmd)
            self.assertIn("testuser", called_cmd)
            self.assertIn("secretpass", called_cmd)
            mock_thread.return_value.start.assert_called_once()

    def test_begin_and_poll_qr_login(self):
        from unittest.mock import patch, MagicMock
        from vaporfetch.steamcmd import begin_qr_login, poll_qr_login, auth_session
        import json

        # 1. Test begin_qr_login
        mock_resp_begin = MagicMock()
        mock_resp_begin.__enter__.return_value = mock_resp_begin
        mock_resp_begin.read.return_value = json.dumps({
            "response": {
                "client_id": "123456789",
                "challenge_url": "https://s.team/q/1/123456789",
                "request_id": "abc==",
                "interval": 3,
            }
        }).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp_begin):
            begin_res = begin_qr_login()
            self.assertEqual(begin_res["status"], "success")
            self.assertEqual(begin_res["client_id"], "123456789")
            self.assertEqual(begin_res["challenge_url"], "https://s.team/q/1/123456789")

        # 2. Test poll_qr_login waiting
        mock_resp_poll_waiting = MagicMock()
        mock_resp_poll_waiting.__enter__.return_value = mock_resp_poll_waiting
        mock_resp_poll_waiting.read.return_value = json.dumps({
            "response": {
                "had_remote_interaction": True
            }
        }).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp_poll_waiting):
            poll_res = poll_qr_login("123456789", "abc==")
            self.assertEqual(poll_res["status"], "waiting")
            self.assertTrue(poll_res["had_remote_interaction"])

        # 3. Test poll_qr_login approved
        mock_resp_poll_approved = MagicMock()
        mock_resp_poll_approved.__enter__.return_value = mock_resp_poll_approved
        mock_resp_poll_approved.read.return_value = json.dumps({
            "response": {
                "account_name": "reaper360vr",
                "steamid": "76561198000000000",
                "access_token": "token123",
                "refresh_token": "refresh123",
            }
        }).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp_poll_approved), \
             patch("vaporfetch.steamcmd.save_current_session") as mock_save:
            poll_res2 = poll_qr_login("123456789", "abc==")
            self.assertEqual(poll_res2["status"], "logged_in")
            self.assertEqual(poll_res2["username"], "reaper360vr")
            self.assertEqual(auth_session.status, "logged_in")
            mock_save.assert_called_once()

    def test_fetch_licenses_uses_in_memory_password(self):
        from unittest.mock import patch, MagicMock
        from vaporfetch.steamcmd import fetch_licenses, auth_session

        auth_session.username = "testuser"
        auth_session.pending_password = "SecretPassword123"

        mock_proc = MagicMock()
        mock_proc.stdout = "License packageID 100:\n - Apps : 730, (1 in total)\n"

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            app_ids = fetch_licenses("testuser")
            self.assertIn(730, app_ids)
            # Verify that the command executed included username and password
            called_cmd = mock_run.call_args[0][0]
            self.assertIn("testuser", called_cmd)
            self.assertIn("SecretPassword123", called_cmd)
            self.assertIn("+licenses_print", called_cmd)

        auth_session.reset()

if __name__ == "__main__":
    unittest.main()


