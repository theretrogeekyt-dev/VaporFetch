import unittest
from vaporfetch.steamcmd import (
    parse_progress_line,
    parse_licenses_output,
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

    def test_2fa_detection(self):
        email_prompt = "Steam Guard code: "
        mobile_prompt = "Enter the current code from your Steam Guard Mobile Authenticator app: "
        self.assertTrue(bool(RE_STEAM_GUARD.search(email_prompt)))
        self.assertTrue(bool(RE_STEAM_GUARD.search(mobile_prompt)))

    def test_login_result_detection(self):
        success_line1 = "Logged in OK"
        success_line2 = "Waiting for user info...OK"
        fail_line = "FAILED with result code 5"
        pw_fail = "Invalid Password"

        self.assertTrue(bool(RE_LOGIN_SUCCESS.search(success_line1)))
        self.assertTrue(bool(RE_LOGIN_SUCCESS.search(success_line2)))
        self.assertTrue(bool(RE_LOGIN_FAIL.search(fail_line)))
        self.assertTrue(bool(RE_LOGIN_FAIL.search(pw_fail)))

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

if __name__ == "__main__":
    unittest.main()

