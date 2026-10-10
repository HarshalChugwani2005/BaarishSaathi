import os
import time
import uuid
import boto3

def main():
    table_name = os.environ.get('REPORTS_TABLE_NAME', 'FloodReports')
    dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
    table = dynamodb.Table(table_name)
    
    import sys
    if '--clear' in sys.argv:
        print(f"Clearing seed reports from {table_name}...")
        # Since we don't know the exact reportIds without a scan, we scan for seed=True
        from boto3.dynamodb.conditions import Attr
        response = table.scan(FilterExpression=Attr('seed').eq(True))
        for item in response.get('Items', []):
            table.delete_item(Key={'spotId': item['spotId'], 'reportId': item['reportId']})
        print("Done clearing.")
        return
        
    print(f"Inserting demo seed reports into {table_name}...")
    
    # 5 realistic sample reports across 3 spots
    now = int(time.time())
    
    seeds = [
        {
            'spotId': 'hindmata',
            'severity': 'KNEE',
            'note': 'Water level rising quickly near the flyover.',
            'createdAt': now - (20 * 60) # 20 mins ago
        },
        {
            'spotId': 'hindmata',
            'severity': 'WAIST',
            'note': 'सडक पर बहुत पानी है, गाड़ियाँ फंस रही हैं।',
            'createdAt': now - (35 * 60) # 35 mins ago
        },
        {
            'spotId': 'hindmata',
            'severity': 'ANKLE',
            'note': 'रस्त्यावर पाणी साचायला सुरुवात झाली आहे.',
            'createdAt': now - (85 * 60) # 85 mins ago
        },
        {
            'spotId': 'mahim_causeway',
            'severity': 'IMPASSABLE',
            'note': 'Traffic completely stopped. Do not come this way.',
            'createdAt': now - (45 * 60) # 45 mins ago
        },
        {
            'spotId': 'dadar_tt',
            'severity': 'KNEE',
            'note': 'Knee deep water near the circle.',
            'createdAt': now - (90 * 60) # 90 mins ago
        }
    ]
    
    for idx, s in enumerate(seeds):
        # Fake a distinct reporterHash for each
        reporter_hash = f"seed-hash-{idx}"
        report_id = str(s['createdAt']) + "-" + str(uuid.uuid4())[:8]
        
        item = {
            'spotId': s['spotId'],
            'reportId': report_id,
            'createdAt': s['createdAt'],
            'severity': s['severity'],
            'note': s['note'],
            'reporterHash': reporter_hash,
            'expiresAt': now + (6 * 3600),
            'seed': True
        }
        table.put_item(Item=item)
        
    print("Demo reports seeded successfully!")
    print("Note: This is demo data only. Disclose it in the demo and README.")

if __name__ == '__main__':
    main()
