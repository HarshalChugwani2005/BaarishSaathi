import json
import os
import boto3
import re
from datetime import datetime

dynamodb = boto3.resource('dynamodb', region_name=os.environ.get("AWS_REGION", "ap-south-1"))
sns = boto3.client('sns', region_name=os.environ.get("AWS_REGION", "ap-south-1"))

def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        email = body.get('email', '').strip()
        spot_id = body.get('spotId', '').strip()
        
        if not email or not spot_id:
            return {"statusCode": 400, "headers": {"Access-Control-Allow-Origin": "*"}, "body": json.dumps({"error": "Missing email or spotId"})}
            
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return {"statusCode": 400, "headers": {"Access-Control-Allow-Origin": "*"}, "body": json.dumps({"error": "Invalid email format"})}
            
        table = dynamodb.Table(os.environ.get("TABLE_NAME", "Subscribers"))
        sns_topic_arn = os.environ.get("SNS_TOPIC_ARN")
        
        # Subscribe to SNS with Filter Policy
        response = sns.subscribe(
            TopicArn=sns_topic_arn,
            Protocol='email',
            Endpoint=email,
            Attributes={
                "FilterPolicy": json.dumps({"spotId": [spot_id]})
            },
            ReturnSubscriptionArn=True
        )
        
        table.put_item(Item={
            'email': email,
            'spotId': spot_id,
            'createdAt': datetime.utcnow().isoformat(),
            'status': 'pending_confirmation'
        })
        
        return {
            "statusCode": 200,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"message": "Successfully registered! Please check your email inbox to confirm the subscription to receive alerts."})
        }
    except Exception as e:
        print(f"Error subscribing: {e}")
        return {"statusCode": 500, "headers": {"Access-Control-Allow-Origin": "*"}, "body": json.dumps({"error": str(e)})}
