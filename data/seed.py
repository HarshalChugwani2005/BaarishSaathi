"""
BaarishSaathi - Flood Spots DynamoDB Seed Script
Loads 15 Mumbai chronic waterlogging hotspots from flood_spots.json into DynamoDB.
"""

import json
import os
import sys
from decimal import Decimal
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

def load_seed_data():
    json_path = Path(__file__).parent / "flood_spots.json"
    if not json_path.exists():
        print(f"Error: {json_path} not found.")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        # DynamoDB requires Decimal types instead of standard Python floats
        return json.load(f, parse_float=Decimal)

def seed_spots():
    table_name = os.environ.get("FLOOD_SPOTS_TABLE", os.environ.get("TABLE_NAME", "FloodSpots"))
    region_name = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "ap-south-1"))

    print(f"Connecting to DynamoDB table '{table_name}' in region '{region_name}'...")
    dynamodb = boto3.resource("dynamodb", region_name=region_name)
    table = dynamodb.Table(table_name)

    spots = load_seed_data()
    print(f"Loaded {len(spots)} hotspots from flood_spots.json. Seeding into DynamoDB...")

    success_count = 0
    with table.batch_writer() as batch:
        for spot in spots:
            try:
                batch.put_item(Item=spot)
                print(f" -> Queued spot: {spot['name']} ({spot['spotId']})")
                success_count += 1
            except ClientError as e:
                print(f"Failed to put spot {spot.get('spotId')}: {e.response['Error']['Message']}")

    print(f"\nSuccessfully seeded {success_count}/{len(spots)} flood spots into '{table_name}'.")

if __name__ == "__main__":
    seed_spots()
