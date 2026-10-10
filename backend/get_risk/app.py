import json
import os
import urllib.request
import urllib.error
from decimal import Decimal
import boto3
from datetime import datetime, timedelta
import risk_engine

dynamodb = None
table = None
reports_table_name = os.environ.get("REPORTS_TABLE_NAME", "FloodReports")

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
            
        # Check DynamoDB cache
        now = datetime.utcnow()
        cache_key = 'cachedRiskHeavy' if simulate == 'heavy' else 'cachedRisk'
        cached = spot.get(cache_key)
        
        if cached:
            try:
                cache_time = datetime.fromisoformat(cached.get('timestamp', '2000-01-01T00:00:00'))
                # 15 minute TTL default, but 5 minute if reports are present in the cached data
                cache_data = cached.get('data', {})
                ttl_minutes = 5 if cache_data.get('reports') and cache_data['reports'].get('countLast2h', 0) > 0 else 15
                
                if now - cache_time < timedelta(minutes=ttl_minutes):
                    return {
                        "statusCode": 200,
                        "headers": {"Access-Control-Allow-Origin": "*"},
                        "body": json.dumps(cache_data, cls=DecimalEncoder)
                    }
            except:
                pass
                
        # Fetch recent reports for this spot
        reports = []
        try:
            reports_table = dynamodb.Table(reports_table_name)
            now_ts = int(now.timestamp())
            three_hours_ago = str(now_ts - (3 * 3600))
            from boto3.dynamodb.conditions import Key
            res = reports_table.query(
                KeyConditionExpression=Key('spotId').eq(spot_id) & Key('reportId').gt(three_hours_ago),
                ScanIndexForward=False,
                Limit=50
            )
            # convert Decimal to float/int before passing to risk_engine if needed, but DecimalEncoder handles it at JSON dump. We need to convert for risk_engine math.
            reports = res.get('Items', [])
            for r in reports:
                if 'createdAt' in r:
                    r['createdAt'] = int(r['createdAt'])
        except Exception as e:
            print(f"Failed to fetch reports: {e}")
            
        lat = float(spot.get("lat", 0))
        lng = float(spot.get("lng", 0))
        historical_severity = int(spot.get("historicalSeverity", 1))
        low_lying = bool(spot.get("lowLying", False))
        tide_sensitivity = float(spot.get("tideSensitivity", 0.0))
        
        rain_next_3h = 0.0
        rain_next_24h = 0.0
        precip_prob = 0
        now_ist = now + timedelta(hours=5, minutes=30)
        tide_data = None
        
        if simulate == "heavy":
            rain_next_3h = 25.0
            rain_next_24h = 150.0
            precip_prob = 90
            
            mock_tide_time = now_ist + timedelta(hours=1)
            tide_data = {
                "nextHighTideTime": mock_tide_time.strftime("%I:%M %p").lstrip('0'),
                "nextHighTideHeight": 4.5,
                "isHighTideWindow": True,
                "hoursToNextHighTide": 1.0,
                "tideLevel": "HIGH",
                "coincidesWithRain": True
            }
        else:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}&hourly=precipitation,precipitation_probability&forecast_hours=24"
            req = urllib.request.Request(url, headers={'User-Agent': 'BaarishSaathi/1.0'})
            try:
                with urllib.request.urlopen(req, timeout=5) as res:
                    data = json.loads(res.read().decode())
                    hourly = data.get("hourly", {})
                    precipitation = hourly.get("precipitation", [])
                    probabilities = hourly.get("precipitation_probability", [])
                    
                    if precipitation:
                        rain_next_3h = sum(precipitation[:3])
                        rain_next_24h = sum(precipitation)
                    if probabilities:
                        precip_prob = max(probabilities[:3]) if len(probabilities) >= 3 else max(probabilities)
            except Exception as e:
                print(f"Weather API failed: {e}")
                
            if tide_sensitivity > 0:
                tide_data = risk_engine.fetch_tide_data(19.07, 72.87, now_ist)
                
        score, risk_level, breakdown, tide_data, reports_data = risk_engine.calculate_risk_score(
            rain_next_3h, rain_next_24h, precip_prob, historical_severity, low_lying, tide_sensitivity, tide_data, reports, int(now.timestamp())
        )
        
        # Don't cache full spot details to save DynamoDB write capacity, just what we need
        community_confirmed = reports_data.get('communityConfirmed', False) if reports_data else False
        alert = risk_engine.generate_alert(spot, risk_level, round(rain_next_3h, 2), round(rain_next_24h, 2), tide_data, community_confirmed)
        
        # We must include spotDetails in the result for the frontend
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
        
        if tide_data:
            result['tide'] = tide_data
            
        if reports_data:
            result['reports'] = reports_data
            
        # Clean spot to avoid nested circular updates in DynamoDB
        clean_spot = dict(spot)
        if 'cachedRisk' in clean_spot: del clean_spot['cachedRisk']
        if 'cachedRiskHeavy' in clean_spot: del clean_spot['cachedRiskHeavy']
        result['spotDetails'] = clean_spot
            
        try:
            cache_val = {
                'timestamp': now.isoformat(),
                'data': result
            }
            # Make sure we convert floats to Decimal for DynamoDB and handle existing Decimals
            cache_val = json.loads(json.dumps(cache_val, cls=DecimalEncoder), parse_float=Decimal)
            table.update_item(
                Key={'spotId': spot_id},
                UpdateExpression=f"SET {cache_key} = :val",
                ExpressionAttributeValues={':val': cache_val}
            )
        except Exception as e:
            print(f"Failed to cache risk to DynamoDB: {e}")
        
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
