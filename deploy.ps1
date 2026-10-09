$ErrorActionPreference = 'Stop'

$STACK_NAME = "baarish-saathi"

Write-Host "🚀 Deploying BaarishSaathi SAM Stack..." -ForegroundColor Cyan
sam build
sam deploy --resolve-s3 --stack-name $STACK_NAME --region ap-south-1 --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM --no-confirm-changeset

Write-Host "📦 Extracting CloudFormation outputs..." -ForegroundColor Cyan
$API_URL = aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text
$BUCKET_NAME = aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" --output text
$FRONTEND_URL = aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='FrontendUrl'].OutputValue" --output text

Write-Host "🔗 Injected API URL: $API_URL" -ForegroundColor Green
$API_CLEAN = $API_URL.TrimEnd('/')
$AppJsPath = "frontend\app.js"
(Get-Content $AppJsPath) -replace 'const API_BASE_URL = ".*";', "const API_BASE_URL = `"$API_CLEAN`";" | Set-Content $AppJsPath

Write-Host "📤 Syncing frontend files to S3 bucket: $BUCKET_NAME..." -ForegroundColor Cyan
aws s3 sync frontend/ s3://$BUCKET_NAME/ --delete



Write-Host "=================================================" -ForegroundColor Magenta
Write-Host "✅ Deployment Complete!" -ForegroundColor Green
Write-Host "🌐 Live Frontend URL: $FRONTEND_URL" -ForegroundColor Yellow
Write-Host "=================================================" -ForegroundColor Magenta
