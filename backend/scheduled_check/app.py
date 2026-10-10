import json
import os
import boto3
import urllib.request
from datetime import datetime, timedelta
import risk_engine

dynamodb = boto3.resource('dynamodb', region_name=os.environ.get("AWS_REGION", "ap-south-1"))
sns = boto3.client('sns', region_name=os.environ.get("AWS_REGION", "ap-south-1"))

def lambda_handler(event, context):
    try:
        table_name = os.environ.get("TABLE_NAME", "FloodSpots")
        table = dynamodb.Table(table_name)
        sns_topic_arn = os.environ.get("SNS_TOPIC_ARN")
        
        response = table.scan()
        spots = response.get('Items', [])
        
        now = datetime.utcnow()
        now_ist = now + timedelta(hours=5, minutes=30)
        
        # Fetch tide data once for the whole run since it's same for Mumbai
        tide_cache = risk_engine.fetch_tide_data(19.07, 72.87, now_ist)
        
        for spot in spots:
            spot_id = spot.get('spotId')
            lat = float(spot.get("lat", 0))
            lng = float(spot.get("lng", 0))
            historical = int(spot.get("historicalSeverity", 1))
            low_lying = bool(spot.get("lowLying", False))
            tide_sensitivity = float(spot.get("tideSensitivity", 0.0))
            
            last_alerted = spot.get('lastAlertedAt')
            if last_alerted:
                last_time = datetime.fromisoformat(last_alerted)
                if now - last_time < timedelta(hours=3):
                    print(f"Skipping {spot_id}: Alerted recently.")
                    continue
            
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}&hourly=precipitation,precipitation_probability&forecast_hours=24"
            req = urllib.request.Request(url, headers={'User-Agent': 'BaarishSaathi/1.0'})
            
            rain_3h = 0.0
            rain_24h = 0.0
            prob = 0
            
            try:
                with urllib.request.urlopen(req, timeout=5) as res:
                    data = json.loads(res.read().decode())
                    precipitation = data.get("hourly", {}).get("precipitation", [])
                    probabilities = data.get("hourly", {}).get("precipitation_probability", [])
                    if precipitation:
                        rain_3h = sum(precipitation[:3])
                        rain_24h = sum(precipitation)
                    if probabilities:
                        prob = max(probabilities[:3]) if len(probabilities) >= 3 else max(probabilities)
            except Exception as e:
                print(f"Weather fetch failed for {spot_id}: {e}")
                continue
                
            tide_data = dict(tide_cache) if tide_cache and tide_sensitivity > 0 else None
            
            reports = []
            try:
                reports_table = dynamodb.Table(os.environ.get("REPORTS_TABLE_NAME", "FloodReports"))
                now_ts = int(now.timestamp())
                three_hours_ago = str(now_ts - (3 * 3600))
                from boto3.dynamodb.conditions import Key
                res = reports_table.query(
                    KeyConditionExpression=Key('spotId').eq(spot_id) & Key('reportId').gt(three_hours_ago),
                    ScanIndexForward=False,
                    Limit=50
                )
                reports = res.get('Items', [])
                for r in reports:
                    if 'createdAt' in r:
                        r['createdAt'] = int(r['createdAt'])
            except Exception as e:
                print(f"Scheduled check failed to fetch reports for {spot_id}: {e}")
            
            score, risk_level, breakdown, final_tide_data, reports_data = risk_engine.calculate_risk_score(
                rain_3h, rain_24h, prob, historical, low_lying, tide_sensitivity, tide_data, reports, int(now.timestamp())
            )
            
            if risk_level == "HIGH":
                community_confirmed = reports_data.get('communityConfirmed', False) if reports_data else False
                alert = risk_engine.generate_alert(spot, risk_level, round(rain_3h, 2), round(rain_24h, 2), final_tide_data, community_confirmed)
                english_alert = alert.get("en", "High risk flood alert.")
                
                sns.publish(
                    TopicArn=sns_topic_arn,
                    Message=english_alert,
                    Subject=f"BaarishSaathi HIGH Risk Alert: {spot.get('name')}",
                    MessageAttributes={
                        'spotId': {
                            'DataType': 'String',
                            'StringValue': spot_id
                        }
                    }
                )
                
                table.update_item(
                    Key={'spotId': spot_id},
                    UpdateExpression="SET lastAlertedAt = :val",
                    ExpressionAttributeValues={':val': now.isoformat()}
                )
                print(f"Published HIGH risk alert for {spot_id}")
                
        return {"statusCode": 200, "body": json.dumps({"status": "completed"})}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
