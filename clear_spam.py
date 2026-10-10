import boto3
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
table = dynamodb.Table('FloodReportsTable')

# Scan for all items with 'Spam' in the note and delete them
response = table.scan(FilterExpression=Attr('note').contains('Spam report'))
items = response.get('Items', [])
deleted = 0
for item in items:
    table.delete_item(Key={'spotId': item['spotId'], 'reportId': item['reportId']})
    deleted += 1

print(f"Deleted {deleted} spam reports")
