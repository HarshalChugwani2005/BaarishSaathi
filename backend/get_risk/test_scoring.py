import unittest
import sys
import os

# Add shared_layer to sys.path so we can import risk_engine
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared_layer', 'python'))
import risk_engine

class TestRiskScoring(unittest.TestCase):
    
    def test_low_risk(self):
        # 0 rain, 0 prob, low severity, not low lying, no tide
        score, level, breakdown, tide = risk_engine.calculate_risk_score(0, 0, 0, 1, False)
        self.assertEqual(level, "LOW")
        self.assertLess(score, 35)
        
    def test_high_risk_heavy_rain(self):
        # Heavy rain: 30mm in 3h, 150mm in 24h, 100% prob, high severity, low lying
        score, level, breakdown, tide = risk_engine.calculate_risk_score(30, 150, 100, 5, True)
        self.assertEqual(level, "HIGH")
        self.assertGreater(score, 65)
        
    def test_medium_risk(self):
        # Moderate rain: 15mm in 3h, 60mm in 24h, 80% prob, medium severity (4), low lying
        score, level, breakdown, tide = risk_engine.calculate_risk_score(15, 60, 80, 4, True)
        self.assertEqual(level, "MEDIUM")
        self.assertTrue(35 <= score <= 65)

    def test_score_cap(self):
        # Extreme rain to test capping at 100, must include high tide to reach 100
        tide_data = {"tideLevel": "HIGH", "isHighTideWindow": True}
        score, level, breakdown, tide = risk_engine.calculate_risk_score(100, 500, 100, 5, True, 1.0, tide_data)
        self.assertEqual(score, 100)
        self.assertEqual(level, "HIGH")
        
    def test_heavy_rain_high_tide(self):
        # Heavy rain + high tide (score jumps)
        # 20mm in 3h, 80mm in 24h, 80% prob, high severity, low lying
        # coastal spot (tide_sensitivity=1.0)
        tide_data = {"tideLevel": "HIGH", "isHighTideWindow": True}
        
        # Without tide
        score_no_tide, _, _, _ = risk_engine.calculate_risk_score(20, 80, 80, 5, True, 0.0, None)
        
        # With tide
        score_tide, _, _, _ = risk_engine.calculate_risk_score(20, 80, 80, 5, True, 1.0, tide_data)
        
        # Tide factor (15.0 * 1.0) + compound bonus (10.0) = 25.0 difference
        self.assertEqual(score_tide - score_no_tide, 25)
        
    def test_heavy_rain_low_tide(self):
        # Heavy rain + low tide (lower)
        tide_data_low = {"tideLevel": "LOW", "isHighTideWindow": False}
        tide_data_high = {"tideLevel": "HIGH", "isHighTideWindow": True}
        
        score_low, _, _, _ = risk_engine.calculate_risk_score(30, 150, 100, 5, True, 1.0, tide_data_low)
        score_high, _, _, _ = risk_engine.calculate_risk_score(30, 150, 100, 5, True, 1.0, tide_data_high)
        
        self.assertLess(score_low, score_high)
        # Difference should be (15 * 1.0) + 10 = 25 vs (15 * 0.2) + 0 = 3
        # Which is 22 points.
        self.assertEqual(score_high - score_low, 22)
        
    def test_no_rain_high_tide(self):
        # No rain + high tide (stays LOW)
        tide_data = {"tideLevel": "HIGH", "isHighTideWindow": True}
        score, level, _, _ = risk_engine.calculate_risk_score(0, 0, 0, 1, False, 1.0, tide_data)
        
        self.assertEqual(level, "LOW")
        # Base score (hist=3) + tide_factor(15) = 18. Compound bonus is 0 because rain < 10mm.
        self.assertLess(score, 35)

if __name__ == '__main__':
    unittest.main()
