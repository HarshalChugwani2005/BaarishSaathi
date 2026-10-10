import os
import boto3
import json
from datetime import datetime, timedelta
bedrock = None

def get_bedrock_client():
    global bedrock
    if bedrock is None:
        region = os.environ.get("BEDROCK_REGION", "us-east-1")
        from botocore.config import Config
        config = Config(read_timeout=3, connect_timeout=1, retries={'max_attempts': 1})
        bedrock = boto3.client(service_name='bedrock-runtime', region_name=region, config=config)
    return bedrock

_tide_cache = {}
_tide_cache_time = None

def fetch_tide_data(lat, lng, now):
    global _tide_cache, _tide_cache_time
    # 30-minute TTL cache for tide data
    if _tide_cache_time and (now - _tide_cache_time).total_seconds() < 1800:
        return dict(_tide_cache)

    import urllib.request
    url = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lng}&hourly=sea_level_height_msl&forecast_days=2&timezone=Asia%2FKolkata"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'BaarishSaathi/1.0'})
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode())
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            heights = hourly.get("sea_level_height_msl", [])
            result = analyze_tide(times, heights, now)
            if result:
                _tide_cache = dict(result)
                _tide_cache_time = now
            return result
    except Exception as e:
        print(f"Marine API failed: {e}")
        return None

def analyze_tide(hourly_times, hourly_heights, now):
    if not hourly_times or not hourly_heights:
        return None
    
    # Parse times
    try:
        times = [datetime.fromisoformat(t.replace('Z', '+00:00')) for t in hourly_times]
    except ValueError:
        times = [datetime.strptime(t, "%Y-%m-%dT%H:%M") for t in hourly_times]
        
    heights = [float(h) for h in hourly_heights]
    
    # Filter next 24 hours
    now = now.replace(tzinfo=None)
    future_data = [(t.replace(tzinfo=None), h) for t, h in zip(times, heights) if now <= t.replace(tzinfo=None) <= now + timedelta(hours=24)]
    
    if not future_data:
        return None
        
    future_times, future_heights = zip(*future_data)
    
    # Find local maxima
    peaks = []
    for i in range(1, len(future_heights) - 1):
        if future_heights[i-1] < future_heights[i] and future_heights[i] > future_heights[i+1]:
            peaks.append((future_times[i], future_heights[i]))
            
    # If no peaks in the exact next 24h due to windowing, just find the max
    if not peaks:
        max_idx = future_heights.index(max(future_heights))
        peaks.append((future_times[max_idx], future_heights[max_idx]))
        
    sorted_heights = sorted(future_heights)
    p75_idx = int(len(sorted_heights) * 0.75)
    p50_idx = int(len(sorted_heights) * 0.50)
    p75 = sorted_heights[p75_idx]
    p50 = sorted_heights[p50_idx]
    
    next_high_tide_time, next_high_tide_height = peaks[0]
    hours_to_next = (next_high_tide_time - now).total_seconds() / 3600.0
    
    is_high_tide_window = False
    for pt, ph in peaks:
        if ph >= p75 and 0 <= (pt - now).total_seconds() / 3600.0 <= 3:
            is_high_tide_window = True
            break
            
    if next_high_tide_height >= p75:
        tide_level = "HIGH"
    elif next_high_tide_height >= p50:
        tide_level = "MEDIUM"
    else:
        tide_level = "LOW"
        
    return {
        "nextHighTideTime": next_high_tide_time.strftime("%I:%M %p").lstrip('0'),
        "nextHighTideHeight": round(next_high_tide_height, 2),
        "isHighTideWindow": is_high_tide_window,
        "hoursToNextHighTide": round(hours_to_next, 1),
        "tideLevel": tide_level
    }

def reports_bump(reports, now_ts, forecast_rain):
    if not reports:
        return 0.0, 0, 0, False
        
    recent_reports = []
    seen_hashes = set()
    latest_report_at = 0
    
    for r in reports:
        created_at = r.get('createdAt', 0)
        age_seconds = now_ts - created_at
        if age_seconds <= 7200 and age_seconds >= 0: # 2 hours
            if created_at > latest_report_at:
                latest_report_at = created_at
            h = r.get('reporterHash')
            if h and h not in seen_hashes:
                seen_hashes.add(h)
                recent_reports.append(r)
                
    if not recent_reports:
        return 0.0, 0, 0, False
        
    weighted_sum = 0.0
    reporters_last_hour = 0
    has_report_older_than_30m = False
    
    for r in recent_reports:
        age_seconds = now_ts - r.get('createdAt', 0)
        age_minutes = age_seconds / 60.0
        
        if age_minutes <= 60:
            reporters_last_hour += 1
        if age_minutes > 30:
            has_report_older_than_30m = True
            
        if age_minutes <= 30:
            recency_weight = 1.0
        else:
            recency_weight = 1.0 - ((age_minutes - 30) * (0.7 / 90.0))
            
        sev = r.get('severity')
        sev_weight = 0.5 # ANKLE
        if sev == 'KNEE': sev_weight = 1.0
        elif sev == 'WAIST': sev_weight = 1.5
        elif sev == 'IMPASSABLE': sev_weight = 2.0
        
        weighted_sum += (recency_weight * sev_weight)
        
    bump = min(20.0, 6.0 * weighted_sum)
    
    if forecast_rain == 0 and not has_report_older_than_30m:
        bump = min(bump, 10.0)
        
    community_confirmed = (reporters_last_hour >= 3)
    
    return bump, len(recent_reports), latest_report_at, community_confirmed

def calculate_risk_score(rain_next_3h, rain_next_24h, precip_prob, historical_severity, low_lying, tide_sensitivity=0.0, tide_data=None, reports=None, now_ts=0):
    rain_3h_normalized = min(rain_next_3h / 50.0, 1.0)
    rain_24h_normalized = min(rain_next_24h / 150.0, 1.0)
    prob_normalized = min(precip_prob / 100.0, 1.0)
    hist_normalized = min(historical_severity / 5.0, 1.0)
    
    tide_level_multiplier = 0.0
    is_high_tide_window = False
    coincides_with_rain = False
    
    if tide_data:
        tide_level = tide_data.get('tideLevel', 'LOW')
        is_high_tide_window = tide_data.get('isHighTideWindow', False)
        
        if tide_level == 'HIGH':
            tide_level_multiplier = 1.0
        elif tide_level == 'MEDIUM':
            tide_level_multiplier = 0.6
        else:
            tide_level_multiplier = 0.2
            
        if rain_next_3h >= 10.0 and is_high_tide_window:
            coincides_with_rain = True

    tide_factor = 15.0 * tide_sensitivity * tide_level_multiplier
    compound_bonus = 10.0 * tide_sensitivity if coincides_with_rain else 0.0

    r_bump, r_count, r_latest, community_confirmed = reports_bump(reports, now_ts, rain_next_3h)

    score = (
        rain_3h_normalized * 35.0 +
        rain_24h_normalized * 20.0 +
        prob_normalized * 10.0 +
        hist_normalized * 15.0 +
        (5.0 if low_lying else 0.0) +
        tide_factor +
        compound_bonus +
        r_bump
    )
    score = min(round(score), 100)
    
    if score < 35:
        risk_level = "LOW"
    elif score <= 65:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"
        
    breakdown = {
        "rain_3h_score": round(rain_3h_normalized * 35.0, 2),
        "rain_24h_score": round(rain_24h_normalized * 20.0, 2),
        "precip_prob_score": round(prob_normalized * 10.0, 2),
        "historical_score": round(hist_normalized * 15.0, 2),
        "low_lying_score": 5.0 if low_lying else 0.0,
        "tide_factor": round(tide_factor, 2),
        "compound_bonus": round(compound_bonus, 2),
        "reports": round(r_bump, 2)
    }
    
    if tide_data:
        tide_data['coincidesWithRain'] = coincides_with_rain
        
    reports_data = None
    if reports is not None:
        reports_data = {
            "countLast2h": r_count,
            "latestReportAt": r_latest,
            "communityConfirmed": community_confirmed
        }
        
    return score, risk_level, breakdown, tide_data, reports_data

def generate_alert(spot, risk_level, rain_3h, rain_24h, tide_data=None, community_confirmed=False):
    route = spot.get('alternateRoute', 'an alternate route').replace('Use ', '').replace('Take ', '').rstrip('.')
    
    tide_context_en = ""
    tide_context_hi = ""
    tide_context_mr = ""
    
    if tide_data and tide_data.get('coincidesWithRain'):
        tide_time = tide_data.get('nextHighTideTime', 'soon')
        tide_context_en = f" Heavy rain coincides with high tide at {tide_time}, so drainage will be slow."
        tide_context_hi = f" भारी बारिश {tide_time} पर उच्च ज्वार के साथ मेल खाती है, इसलिए जल निकासी धीमी होगी।"
        tide_context_mr = f" {tide_time} च्या भरतीसह जोरदार पाऊस असल्यामुळे पाण्याचा निचरा संथ होईल."

    community_context_en = " Residents are also reporting water on the road." if community_confirmed else ""
    community_context_hi = " निवासी भी सड़क पर पानी की सूचना दे रहे हैं।" if community_confirmed else ""
    community_context_mr = " स्थानिक नागरिक देखील रस्त्यावर पाणी साचल्याची माहिती देत आहेत." if community_confirmed else ""

    fallback = {
        "en": f"Risk level at {spot['name']} is {risk_level}. Next 3h rainfall: {rain_3h}mm.{tide_context_en}{community_context_en} Consider using {route}.",
        "hi": f"{spot['name']} पर जोखिम का स्तर {risk_level} है। 3 घंटे में {rain_3h}mm बारिश।{tide_context_hi}{community_context_hi} कृपया {route} का उपयोग करें।",
        "mr": f"{spot['name']} येथे धोक्याची पातळी {risk_level} आहे. पुढील ३ तासात {rain_3h}mm पाऊस.{tide_context_mr}{community_context_mr} कृपया {route}चा वापर करा."
    }
    try:
        client = get_bedrock_client()
        model_id = "us.amazon.nova-lite-v1:0"
        
        prompt = f"""You are a calm, practical weather routing assistant for Mumbai commuters.
The current status for {spot['name']}:
- Risk Level: {risk_level}
- Expected rain next 3 hours: {rain_3h} mm
- Expected rain next 24 hours: {rain_24h} mm
- Alternate Route: {spot.get('alternateRoute', 'None specified')}"""

        if tide_data and tide_data.get('coincidesWithRain'):
            prompt += f"\n- High Tide Alert: Heavy rain coincides with high tide at {tide_data.get('nextHighTideTime')}, leading to slow drainage."

        if community_confirmed:
            prompt += "\n- Community Confirmed: Residents are also reporting water on the road."

        prompt += """\n
Task: Write a 2-sentence plain-language alert.
Mention the spot name, the risk level, the time window, and the alternate route."""
        
        if tide_data and tide_data.get('coincidesWithRain'):
            prompt += " Also briefly mention the high tide making drainage slow."
            
        if community_confirmed:
            prompt += " Mention that residents are also reporting water on the road."
            
        prompt += """\nNever invent facts beyond the data given. Use only the provided numbers.
Return ONLY a valid JSON object with keys "en" (English), "hi" (Hindi), and "mr" (Marathi). Do not include markdown formatting or backticks."""

        messages = [{"role": "user", "content": [{"text": prompt}]}]
        response = client.converse(
            modelId=model_id,
            messages=messages,
            inferenceConfig={"temperature": 0.1, "maxTokens": 300}
        )
        response_text = response['output']['message']['content'][0]['text'].strip()
        if response_text.startswith("```json"): response_text = response_text[7:]
        if response_text.endswith("```"): response_text = response_text[:-3]
        if response_text.startswith("```"): response_text = response_text[3:]
        return json.loads(response_text.strip())
    except Exception as e:
        print(f"Bedrock failure: {e}")
        return fallback
