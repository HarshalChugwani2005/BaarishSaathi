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
        
        try:
            response = sns.subscribe(
                TopicArn=sns_topic_arn,
                Protocol='email',
                Endpoint=email,
                Attributes={
                    "FilterPolicy": json.dumps({"spotId": [spot_id]})
                },
                ReturnSubscriptionArn=True
            )
        except sns.exceptions.InvalidParameterException as e:
            if "Subscription already exists with different attributes" in str(e):
                # Find the existing subscription
                paginator = sns.get_paginator('list_subscriptions_by_topic')
                existing_sub = None
                for page in paginator.paginate(TopicArn=sns_topic_arn):
                    for sub in page['Subscriptions']:
                        if sub['Endpoint'] == email:
                            existing_sub = sub
                            break
                    if existing_sub:
                        break
                        
                if existing_sub:
                    sub_arn = existing_sub['SubscriptionArn']
                    if sub_arn == 'PendingConfirmation':
                        return {
                            "statusCode": 200,
                            "headers": {"Access-Control-Allow-Origin": "*"},
                            "body": json.dumps({"message": "You have a pending subscription. Please check your email to confirm it first!"})
                        }
                    else:
                        # Get current attributes
                        attrs = sns.get_subscription_attributes(SubscriptionArn=sub_arn)
                        current_policy_str = attrs.get('Attributes', {}).get('FilterPolicy', '{}')
                        try:
                            current_policy = json.loads(current_policy_str)
                            spots = current_policy.get('spotId', [])
                            if spot_id not in spots:
                                spots.append(spot_id)
                                current_policy['spotId'] = spots
                                # Update attributes
                                sns.set_subscription_attributes(
                                    SubscriptionArn=sub_arn,
                                    AttributeName='FilterPolicy',
                                    AttributeValue=json.dumps(current_policy)
                                )
                            else:
                                return {
                                    "statusCode": 200,
                                    "headers": {"Access-Control-Allow-Origin": "*"},
                                    "body": json.dumps({"message": "You are already subscribed to receive alerts for this spot!"})
                                }
                        except Exception as inner_e:
                            print(f"Failed to update existing filter policy: {inner_e}")
                            raise inner_e
            else:
                raise e
        
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
