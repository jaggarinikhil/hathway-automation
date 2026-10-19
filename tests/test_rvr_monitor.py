import unittest
from datetime import datetime, timedelta
from rvr_monitor.monitor import IST, assess, in_window


class RvrTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 19, 6, 0, tzinfo=IST)
        self.groups = {"six": list("abcdef"), "three": list("xyz")}
        self.accounts = {u: "active" for users in self.groups.values() for u in users}

    def test_half_confirm_and_suppress_then_rearm(self):
        online = set("defyz")  # 3/6 and 1/3 offline
        first, alerts = assess(self.groups, self.accounts, online, {}, self.now)
        self.assertEqual(alerts, [])
        second, alerts = assess(self.groups, self.accounts, online, first, self.now + timedelta(minutes=10))
        self.assertEqual(alerts, ["six"])
        second["six"]["notified"] = True
        third, alerts = assess(self.groups, self.accounts, online, second, self.now + timedelta(minutes=20))
        self.assertEqual(alerts, [])
        recovered, alerts = assess(self.groups, self.accounts, set(self.accounts), third, self.now + timedelta(minutes=30))
        self.assertEqual(alerts, [])
        self.assertFalse(recovered["six"]["notified"])

    def test_round_up_and_zero_active(self):
        state, _ = assess(self.groups, self.accounts, set("abcdefz"), {}, self.now)
        self.assertEqual(state["three"]["threshold"], 2)
        _, alerts = assess(self.groups, self.accounts, set("abcdefz"), state, self.now + timedelta(minutes=10))
        self.assertEqual(alerts, ["three"])
        accounts = {u: "expired" for u in self.accounts}
        state, alerts = assess(self.groups, accounts, set(), {}, self.now)
        self.assertFalse(alerts)
        self.assertEqual(state["six"]["streak"], 0)

    def test_missing_users_fail_closed(self):
        del self.accounts["a"]
        with self.assertRaises(ValueError):
            assess(self.groups, self.accounts, set(), {}, self.now)

    def test_overnight_and_long_gaps_do_not_confirm(self):
        state, _ = assess(self.groups, self.accounts, set(), {}, self.now)
        for gap in (16, 60, 1440):
            _, alerts = assess(self.groups, self.accounts, set(), state, self.now + timedelta(minutes=gap))
            self.assertEqual(alerts, [])

    def test_window(self):
        for hour, minute, expected in [(5,59,False),(6,0,True),(11,59,True),(12,0,True),(12,1,True),(23,0,True),(23,59,True),(0,0,False)]:
            self.assertEqual(in_window(self.now.replace(hour=hour, minute=minute)), expected)


if __name__ == "__main__":
    unittest.main()
