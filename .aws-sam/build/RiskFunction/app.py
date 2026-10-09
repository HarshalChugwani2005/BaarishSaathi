import json
import os
import urllib.request
import urllib.error
from decimal import Decimal
import boto3
import risk_engine

dynamodb = None
table = None

def get_table():
    global dynamodb, table
    if table is None:
        table_name = os.environ.get("TABLE_NAME", "FloodSpots")
        region = os.environ.get("AWS_REGION", "ap-south-1")
        dynamodb = boto3.resource("dynamodb", region_name=region)
        table = dynamodb.Table(table_name)
    return table

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super(DecimalEncoder, self).default(obj)



def lambda_handler(event, context):
    try:
        query_params = event.get("queryStringParameters") or {}
        spot_id = query_params.get("spotId")
        simulate = query_params.get("simulate")
        
        if not spot_id:
            return {
                "statusCode": 400,
                "headers": {"Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "Missing spotId"})
            }
            
        table = get_table()
        response = table.get_item(Key={"spotId": spot_id})
        spot = response.get("Item")
        
        if not spot:
            return {
                "statusCode": 404,
                "headers": {"Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "Spot not found"})
            }
            
        lat = float(spot.get("lat", 0))
        lng = float(spot.get("lng", 0))
        historical_severity = int(spot.get("historicalSeverity", 1))
        low_lying = bool(spot.get("lowLying", False))
        
        rain_next_3h = 0.0
        rain_next_24h = 0.0
        precip_prob = 0
        
        if simulate == "heavy":
            rain_next_3h = 25.0
            rain_next_24h = 150.0
            precip_prob = 90
        else:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}&hourly=precipitation,precipitation_probability&forecast_hours=24"
            req = urllib.request.Request(url, headers={'User-Agent': 'BaarishSaathi/1.0'})
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode())
                hourly = data.get("hourly", {})
                precipitation = hourly.get("precipitation", [])
                probabilities = hourly.get("precipitation_probability", [])
                
                if precipitation:
                    rain_next_3h = sum(precipitation[:3])
                    rain_next_24h = sum(precipitation)
                if probabilities:
                    # Take max probability from the next 3 hours as representative
                    precip_prob = max(probabilities[:3]) if len(probabilities) >= 3 else max(probabilities)
                    
        score, risk_level, breakdown = risk_engine.calculate_risk_score(
            rain_next_3h, rain_next_24h, precip_prob, historical_severity, low_lying
        )
        
        alert = risk_engine.generate_alert(spot, risk_level, round(rain_next_3h, 2), round(rain_next_24h, 2))
        
        result = {
            "spotDetails": spot,
            "riskLevel": risk_level,
            "score": score,
            "rainNext3h": round(rain_next_3h, 2),
            "rainNext24h": round(rain_next_24h, 2),
            "precipitationProbability": precip_prob,
            "breakdown": breakdown,
            "alternateRoute": spot.get("alternateRoute", ""),
            "alert": alert
        }
        
        return {
            "statusCode": 200,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps(result, cls=DecimalEncoder)
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "statusCode": 500,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": str(e)})
        }
