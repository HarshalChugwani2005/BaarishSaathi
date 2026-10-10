import unittest
import time
from backend.shared_layer.python.risk_engine import reports_bump

class TestReportsBump(unittest.TestCase):
    
    def test_no_reports(self):
        bump, count, latest, confirmed = reports_bump([], 1000, 50.0)
        self.assertEqual(bump, 0.0)
        self.assertEqual(count, 0)
        self.assertFalse(confirmed)
        
    def test_one_report_ankle(self):
        now = 1000
        reports = [
            {'reporterHash': 'h1', 'severity': 'ANKLE', 'createdAt': now - 60}
        ]
        bump, count, latest, confirmed = reports_bump(reports, now, 50.0)
        # 1 report < 30min -> recency=1.0, ANKLE=0.5. sum=0.5 -> bump=6*0.5=3.0
        self.assertEqual(bump, 3.0)
        self.assertEqual(count, 1)
        self.assertFalse(confirmed)
        
    def test_three_distinct_reporters_big_bump(self):
        now = 3000
        reports = [
            {'reporterHash': 'h1', 'severity': 'IMPASSABLE', 'createdAt': now - 100},
            {'reporterHash': 'h2', 'severity': 'WAIST', 'createdAt': now - 200},
            {'reporterHash': 'h3', 'severity': 'KNEE', 'createdAt': now - 300}
        ]
        bump, count, latest, confirmed = reports_bump(reports, now, 50.0)
        # All < 30m -> weights 1.0. Sev: 2.0 + 1.5 + 1.0 = 4.5. sum=4.5 -> bump=6*4.5=27 -> capped at 20.0
        self.assertEqual(bump, 20.0)
        self.assertEqual(count, 3)
        self.assertTrue(confirmed)
        
    def test_spammer(self):
        now = 1000
        reports = [
            {'reporterHash': 'spammer', 'severity': 'IMPASSABLE', 'createdAt': now - 10},
            {'reporterHash': 'spammer', 'severity': 'IMPASSABLE', 'createdAt': now - 20},
            {'reporterHash': 'spammer', 'severity': 'IMPASSABLE', 'createdAt': now - 30},
            {'reporterHash': 'spammer', 'severity': 'IMPASSABLE', 'createdAt': now - 40}
        ]
        bump, count, latest, confirmed = reports_bump(reports, now, 50.0)
        # Only 1 distinct hash counts. bump = 6 * (1.0 * 2.0) = 12.0
        self.assertEqual(bump, 12.0)
        self.assertEqual(count, 1) # count of processed distinct reports
        self.assertFalse(confirmed)
        
    def test_decay_old_reports(self):
        now = 10000
        # 1 hour ago (60 mins)
        reports = [
            {'reporterHash': 'h1', 'severity': 'KNEE', 'createdAt': now - 3600}
        ]
        bump, count, latest, confirmed = reports_bump(reports, now, 50.0)
        # age=60m. recency = 1.0 - (30)*(0.7/90) = 1.0 - (21/90) = 1.0 - 0.233 = 0.766
        # sev=1.0. sum=0.766. bump = 6 * 0.766 = 4.6
        self.assertTrue(4.0 < bump < 5.0)
        
    def test_dry_day_cap_no_old_confirm(self):
        now = 1000
        # 1 fresh report on a day with 0 forecast rain
        reports = [
            {'reporterHash': 'h1', 'severity': 'IMPASSABLE', 'createdAt': now - 60}
        ]
        bump, count, latest, confirmed = reports_bump(reports, now, 0.0)
        # Normally bump = 6 * (1.0 * 2.0) = 12.0, but capped at 10.0 because no report older than 30m
        self.assertEqual(bump, 10.0)
        
    def test_dry_day_cap_with_old_confirm(self):
        now = 4000
        # fresh report, but also an older report backing it up
        reports = [
            {'reporterHash': 'h1', 'severity': 'IMPASSABLE', 'createdAt': now - 60}, # 1m ago
            {'reporterHash': 'h2', 'severity': 'KNEE', 'createdAt': now - 2400} # 40m ago
        ]
        bump, count, latest, confirmed = reports_bump(reports, now, 0.0)
        # h1 bump = 6 * (1.0 * 2.0) = 12
        # h2 bump = 6 * ((1.0 - (10)*(0.7/90)) * 1.0) = 6 * (1 - 0.077) = 5.53
        # Total > 10. Since we have an older report, the cap of 10 is NOT applied.
        self.assertTrue(bump > 10.0)

if __name__ == '__main__':
    unittest.main()
