#!/bin/bash
set -e

STACK_NAME="baarish-saathi"

echo "🚀 Deploying BaarishSaathi SAM Stack..."
sam build
sam deploy --resolve-s3 --stack-name $STACK_NAME --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM --no-confirm-changeset

echo "📦 Extracting CloudFormation outputs..."
API_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text)
BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" --output text)
CF_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" --output text)
FRONTEND_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='FrontendUrl'].OutputValue" --output text)

echo "🔗 Injected API URL: $API_URL"
# Remove trailing slash for uniformity if present, then replace in app.js
API_CLEAN=${API_URL%/}
sed -i -E "s|const API_BASE_URL = \".*\";|const API_BASE_URL = \"$API_CLEAN\";|" frontend/app.js

echo "📤 Syncing frontend files to S3 bucket: $BUCKET_NAME..."
aws s3 sync frontend/ s3://$BUCKET_NAME/ --delete

echo "🔄 Invalidating CloudFront cache ($CF_ID)..."
aws cloudfront create-invalidation --distribution-id $CF_ID --paths "/*"

echo "================================================="
echo "✅ Deployment Complete!"
echo "🌐 Live Frontend URL: $FRONTEND_URL"
echo "================================================="
