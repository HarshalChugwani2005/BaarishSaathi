import json
import os
import boto3
from decimal import Decimal

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
        table = get_table()
        response = table.scan()
        items = response.get('Items', [])
        
        return {
            "statusCode": 200,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps(items, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error fetching spots: {e}")
        return {
            "statusCode": 500,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": str(e)})
        }
