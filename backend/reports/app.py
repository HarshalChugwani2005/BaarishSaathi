import json
import os
import time
import uuid
import hashlib
import boto3
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr
from botocore.config import Config

dynamodb = boto3.resource('dynamodb')
region = os.environ.get('AWS_REGION', 'ap-south-1')
s3_client = boto3.client('s3', config=Config(region_name=region, signature_version='s3v4', s3={'addressing_style': 'virtual', 'region_name': region}))

REPORTS_TABLE_NAME = os.environ.get('REPORTS_TABLE')
PHOTOS_BUCKET_NAME = os.environ.get('PHOTOS_BUCKET')
SALT = os.environ.get('SALT', 'default-salt')

# Helper to handle Decimal serialization
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def get_reporter_hash(event):
    request_context = event.get('requestContext', {})
    http = request_context.get('http', {})
    source_ip = http.get('sourceIp', 'unknown')
    # Hash IP + salt
    return hashlib.sha256(f"{source_ip}{SALT}".encode('utf-8')).hexdigest()

def lambda_handler(event, context):
    route_key = event.get('routeKey', '')
    
    if route_key == 'POST /reports/upload-url':
        return handle_upload_url(event)
    elif route_key == 'POST /reports':
        return handle_post_report(event)
    elif route_key == 'GET /reports':
        return handle_get_reports(event)
    else:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": "Not Found"})
        }

def handle_upload_url(event):
    try:
        body = json.loads(event.get('body', '{}'))
        content_type = body.get('contentType', '')
        
        if content_type not in ['image/jpeg', 'image/png']:
            return response(400, {"error": "Invalid content type. Only image/jpeg and image/png allowed."})
            
        file_uuid = str(uuid.uuid4())
        ext = 'jpg' if 'jpeg' in content_type else 'png'
        photo_key = f"reports/{file_uuid}.{ext}"
        
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': PHOTOS_BUCKET_NAME,
                'Key': photo_key,
                'ContentType': content_type
            },
            ExpiresIn=300
        )
        
        return response(200, {
            "uploadUrl": presigned_url,
            "photoKey": photo_key
        })
    except Exception as e:
        print(f"Upload URL error: {e}")
        return response(500, {"error": "Failed to generate upload URL."})

def handle_post_report(event):
    try:
        body = json.loads(event.get('body', '{}'))
        spot_id = body.get('spotId')
        severity = body.get('severity')
        note = body.get('note', '')[:140]
        photo_key = body.get('photoKey')
        
        if not spot_id or not severity:
            return response(400, {"error": "spotId and severity are required."})
            
        if severity not in ["ANKLE", "KNEE", "WAIST", "IMPASSABLE"]:
            return response(400, {"error": "Invalid severity."})
            
        reporter_hash = get_reporter_hash(event)
        now = int(time.time())
        table = dynamodb.Table(REPORTS_TABLE_NAME)
        
        # Rate limit check (using the GSI ReporterIndex)
        try:
            one_hour_ago = str(now - 3600)
            res = table.query(
                IndexName='ReporterIndex',
                KeyConditionExpression=Key('reporterHash').eq(reporter_hash) & Key('reportId').gt(one_hour_ago)
            )
            if res.get('Count', 0) >= 3:
                return response(429, {"error": "You can only submit 3 reports per hour. Thanks for your help!"})
        except Exception as e:
            print(f"Rate limit check failed: {e}")
            # Continue anyway, don't block on rate limit errors
            pass
            
        if photo_key:
            # Validate it exists in S3
            try:
                s3_client.head_object(Bucket=PHOTOS_BUCKET_NAME, Key=photo_key)
            except Exception:
                return response(400, {"error": "Photo not found in storage. Ensure upload completed."})
        
        report_id = str(now) + "-" + str(uuid.uuid4())[:8]
        expires_at = now + (6 * 3600)
        
        item = {
            'spotId': spot_id,
            'reportId': report_id,
            'createdAt': now,
            'severity': severity,
            'note': note,
            'reporterHash': reporter_hash,
            'expiresAt': expires_at
        }
        if photo_key:
            item['photoKey'] = photo_key
            
        table.put_item(Item=item)
        
        return response(201, item)
    except Exception as e:
        print(f"Post report error: {e}")
        return response(500, {"error": "Internal Server Error"})

def handle_get_reports(event):
    try:
        params = event.get('queryStringParameters', {}) or {}
        spot_id = params.get('spotId')
        
        if not spot_id:
            return response(400, {"error": "spotId is required"})
            
        table = dynamodb.Table(REPORTS_TABLE_NAME)
        now = int(time.time())
        three_hours_ago = str(now - (3 * 3600))
        
        res = table.query(
            KeyConditionExpression=Key('spotId').eq(spot_id) & Key('reportId').gt(three_hours_ago),
            ScanIndexForward=False, # Newest first
            Limit=50
        )
        
        items = res.get('Items', [])
        
        # Clean up output, deduplicate by reporterHash, and generate presigned GET urls
        output = []
        seen_hashes = set()
        
        for item in items:
            h = item.get('reporterHash')
            if h and h in seen_hashes:
                continue
            if h:
                seen_hashes.add(h)
                
            out_item = {
                'reportId': item.get('reportId'),
                'createdAt': int(item.get('createdAt')),
                'severity': item.get('severity'),
                'note': item.get('note', '')
            }
            if item.get('photoKey'):
                try:
                    presigned_get = s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': PHOTOS_BUCKET_NAME, 'Key': item.get('photoKey')},
                        ExpiresIn=900 # 15 minutes
                    )
                    out_item['photoUrl'] = presigned_get
                except Exception:
                    pass
            output.append(out_item)
            
        return response(200, output)
    except Exception as e:
        print(f"Get reports error: {e}")
        return response(500, {"error": "Internal Server Error"})

def response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(body, cls=DecimalEncoder)
    }
