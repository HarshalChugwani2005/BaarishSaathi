import unittest
from app import calculate_risk_score

class TestRiskScoring(unittest.TestCase):
    
    def test_low_risk(self):
        # 0 rain, 0 prob, low severity, not low lying
        score, level, breakdown = calculate_risk_score(0, 0, 0, 1, False)
        self.assertEqual(level, "LOW")
        self.assertLess(score, 35)
        
    def test_high_risk_heavy_rain(self):
        # Heavy rain: 30mm in 3h, 150mm in 24h, 100% prob, high severity, low lying
        score, level, breakdown = calculate_risk_score(30, 150, 100, 5, True)
        self.assertEqual(level, "HIGH")
        self.assertGreater(score, 65)
        
    def test_medium_risk(self):
        # Moderate rain: 10mm in 3h, 30mm in 24h, 50% prob, medium severity (3), low lying
        score, level, breakdown = calculate_risk_score(10, 30, 50, 3, True)
        self.assertEqual(level, "MEDIUM")
        self.assertTrue(35 <= score <= 65)

    def test_score_cap(self):
        # Extreme rain to test capping at 100
        score, level, breakdown = calculate_risk_score(100, 500, 100, 5, True)
        self.assertEqual(score, 100)
        self.assertEqual(level, "HIGH")

if __name__ == '__main__':
    unittest.main()
