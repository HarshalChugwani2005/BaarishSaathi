import os
import boto3
import json

bedrock = None

def get_bedrock_client():
    global bedrock
    if bedrock is None:
        region = os.environ.get("BEDROCK_REGION", "us-east-1")
        from botocore.config import Config
        config = Config(read_timeout=3, connect_timeout=1, retries={'max_attempts': 1})
        bedrock = boto3.client(service_name='bedrock-runtime', region_name=region, config=config)
    return bedrock

def calculate_risk_score(rain_next_3h, rain_next_24h, precip_prob, historical_severity, low_lying):
    rain_3h_normalized = min(rain_next_3h / 50.0, 1.0)
    rain_24h_normalized = min(rain_next_24h / 150.0, 1.0)
    prob_normalized = min(precip_prob / 100.0, 1.0)
    hist_normalized = min(historical_severity / 5.0, 1.0)
    
    score = (
        rain_3h_normalized * 40.0 +
        rain_24h_normalized * 25.0 +
        prob_normalized * 10.0 +
        hist_normalized * 15.0 +
        (10.0 if low_lying else 0.0)
    )
    score = min(round(score), 100)
    
    if score < 35:
        risk_level = "LOW"
    elif score <= 65:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"
        
    breakdown = {
        "rain_3h_score": round(rain_3h_normalized * 40.0, 2),
        "rain_24h_score": round(rain_24h_normalized * 25.0, 2),
        "precip_prob_score": round(prob_normalized * 10.0, 2),
        "historical_score": round(hist_normalized * 15.0, 2),
        "low_lying_score": 10.0 if low_lying else 0.0
    }
    return score, risk_level, breakdown

def generate_alert(spot, risk_level, rain_3h, rain_24h):
    route = spot.get('alternateRoute', 'an alternate route').replace('Use ', '').replace('Take ', '').rstrip('.')
    fallback = {
        "en": f"Risk level at {spot['name']} is {risk_level}. Next 3h rainfall: {rain_3h}mm. Consider using {route}.",
        "hi": f"{spot['name']} पर जोखिम का स्तर {risk_level} है। 3 घंटे में {rain_3h}mm बारिश। कृपया {route} का उपयोग करें।",
        "mr": f"{spot['name']} येथे धोक्याची पातळी {risk_level} आहे. पुढील ३ तासात {rain_3h}mm पाऊस. कृपया {route}चा वापर करा."
    }
    try:
        client = get_bedrock_client()
        model_id = "us.amazon.nova-lite-v1:0"
        prompt = f"""You are a calm, practical weather routing assistant for Mumbai commuters.
The current status for {spot['name']}:
- Risk Level: {risk_level}
- Expected rain next 3 hours: {rain_3h} mm
- Expected rain next 24 hours: {rain_24h} mm
- Alternate Route: {spot.get('alternateRoute', 'None specified')}

Task: Write a 2-sentence plain-language alert.
Mention the spot name, the risk level, the time window, and the alternate route.
Never invent facts beyond the data given.
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
