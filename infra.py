# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "aws-cdk-lib>=2.233.0",
#     "constructs>=10.4.4",
# ]
# ///
import hashlib
import json
import os
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_apigateway as apigw,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_s3 as s3,
    aws_ssm as ssm,
)
from constructs import Construct

THIS_DIR = Path(__file__).parent

S3_BUCKET_NAME = os.environ["S3_BUCKET_NAME"]

_assets_to_exclude: list[str] = [
    "scripts/*",
    "tests/*",
    "docs/*",
    ".vscode",
    "*.env",
    ".venv",
    "*.pyc",
    "__pycache__",
    "*cache*",
    ".DS_Store",
    ".git",
    ".github",
]

# Create a Lambda function & Lambda Layer
# ref: https://docs.aws.amazon.com/lambda/latest/dg/chapter-layers.html#configuration-layers-path
# ref: https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.LayerVersion.html
# ref: https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3_assets.AssetOptions.html
# ref: https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.BundlingOptions.html


class FilesApiCdkStack(Stack):
    """Files API CDK Stack"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create an S3 bucket
        files_api_bucket = s3.Bucket(
            self,
            id="FilesApiBucket",
            bucket_name=S3_BUCKET_NAME,
            auto_delete_objects=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Create a Secret to store OpenAI API Key

        # CloudFormation does not support creating SecureString parameters.
        # So, we manually create the parameter of type SecureString in the console, then reference it here in CDK.
        # Reference an existing SecureString parameter from SSM Parameter Store
        ssm_openai_api_secret_key = ssm.StringParameter.from_secure_string_parameter_attributes(
            self,
            id="ExistingOpenAIApiSecretKey",
            parameter_name="/files-api/openai-api-key",
            version=1,
        )
        # ^^^This parameter should contain the same OpenAI API Key as in the Secrets Manager secret.
        # ^^^You need to manually create this parameter in the console and delete it when the stack is destroyed.

        # Create a Lambda function & Lambda Layer
        files_api_lambda_layer = _lambda.LayerVersion(
            self,
            id="FilesApiLambdaLayer",
            layer_version_name="files-api-layer",
            description="Lambda layer for Files API",
            compatible_architectures=[_lambda.Architecture.ARM_64],
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            code=_lambda.Code.from_asset(
                path=THIS_DIR.as_posix(),
                display_name="files-api-lambda-layer",
                deploy_time=True,  # delete S3 asset after deployment
                # Only re-build and re-deploy the layer if the dependency files change
                # ref: https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.AssetOptions.html
                asset_hash_type=cdk.AssetHashType.CUSTOM,
                asset_hash=hashlib.sha256(
                    (THIS_DIR / "pyproject.toml").read_bytes() + (THIS_DIR / "uv.lock").read_bytes()
                ).hexdigest(),  # Custom hash based on dependency files
                bundling=cdk.BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        # 0. Upgrade pip to the latest version
                        "pip install --upgrade pip && "
                        # 1. Install uv
                        "pip install uv && "
                        # 2. Use uv to install the 'aws-lambda' group into /asset-output/python
                        "uv pip install --no-cache --link-mode=copy --requirements pyproject.toml --group aws-lambda --target /asset-output/python",
                    ],
                    user="root",  # `user` override to be able to install uv and upgrade pip
                ),
                # bundling={
                #     "image": _lambda.Runtime.PYTHON_3_12.bundling_image,
                #     "command": [...],
                #     "user": "root",  # `user` override to be able to install uv and upgrade pip
                # },
                exclude=_assets_to_exclude,
            ),
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Add AWS parameters and secrets Lambda extension to read secrets from Secrets Manager
        # ref: https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_lambda.html
        # ref: https://docs.aws.amazon.com/lambda/latest/dg/with-secrets-manager.html
        secrets_manager_lambda_extension_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            id="SecretsManagerExtensionLayer",
            layer_version_arn=f"arn:aws:lambda:{self.region}:345057560386:layer:AWS-Parameters-and-Secrets-Lambda-Extension-Arm64:23",
        )
        # ^^^I found the layer ARN here from the AWS docs:
        # https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-integration-lambda-extensions.html#ps-integration-lambda-extensions-add

        # Log group for Lambda function
        # Lambda by default creates a log group of format /aws/lambda/<function-name>
        # But here we are explicitly creating it to set retention and removal policy
        files_api_lambda_log_group = logs.LogGroup(
            self,
            id="FilesApiLambdaLogGroup",
            log_group_name="/aws/lambda/files-api",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        files_api_lambda = _lambda.Function(
            self,
            id="FilesApiLambda",
            function_name="files-api",
            description="Lambda function for Files API",
            runtime=_lambda.Runtime.PYTHON_3_12,
            architecture=_lambda.Architecture.ARM_64,
            memory_size=128,  # default is 128 MB
            handler="files_api.aws_lambda_handler.handler",
            timeout=cdk.Duration.seconds(60),
            code=_lambda.Code.from_asset(
                path=(THIS_DIR / "src").as_posix(),
                exclude=_assets_to_exclude,
            ),
            # Add Lambda Layers for dependencies and AWS Secrets Manager extension
            layers=[files_api_lambda_layer, secrets_manager_lambda_extension_layer],
            # Specify the log group for the Lambda function
            log_group=files_api_lambda_log_group,
            # Enable X-Ray Tracing for the Lambda function
            tracing=_lambda.Tracing.ACTIVE,
            environment={
                "S3_BUCKET_NAME": files_api_bucket.bucket_name,
                "LOGURU_LEVEL": "DEBUG",
                "AWS_EMF_NAMESPACE": "files-api",
                "AWS_XRAY_TRACING_NAME": "Files API",
                "AWS_XRAY_DAEMON_CONTEXT_MISSING": "RUNTIME_ERROR",
                # OpenAI API Key configuration
                # "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
                # "OPENAI_API_SECRET_NAME": openai_api_secret_key.secret_name,
                "OPENAI_API_SSM_PARAMETER_NAME": ssm_openai_api_secret_key.parameter_name,
                # AWS Parameters and Secrets Lambda Extension configuration
                # You can find all the supported environment variables here:
                # https://docs.aws.amazon.com/lambda/latest/dg/with-secrets-manager.html
                "PARAMETERS_SECRETS_EXTENSION_HTTP_PORT": "2773",
                # ^^^Port on which the AWS Parameters and Secrets Lambda Extension listens by default
                "PARAMETERS_SECRETS_EXTENSION_CACHE_ENABLED": "TRUE",
                # Enable caching of secrets to reduce latency and cost
                "SECRETS_MANAGER_TTL": "300",  # Cache secrets for 300 seconds (5 minutes)
                # Time-to-live for cached secrets.
            },
        )

        # Grant the Lambda function permissions to read/write to the S3 bucket
        files_api_bucket.grant_read_write(files_api_lambda)

        # Grant the Lambda function permissions to read the OpenAI API Key secret from SSM Parameter Store
        ssm_openai_api_secret_key.grant_read(files_api_lambda)

        # Grant the Lambda function permissions to write logs to CloudWatch Logs
        files_api_lambda_log_group.grant_write(files_api_lambda)

        # Setup API Gateway with resources and methods

        # Log group for API Gateway access logs
        api_gw_access_log_group_prod = logs.LogGroup(
            self,
            id="FilesApiGwAccessLogGroup",
            log_group_name="/aws/apigateway/access-logs/files-api/prod",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # The LambdaRestApi L2 construct by default creates a `test-invoke-stage` stage for the API

        # I disabled the proxy integration(proxy=False) because on the root path it defined "ANY" method by default which we do not want.
        # For the root path we only want to allow "GET" method to access the OpenAPI docs page.
        files_api_gw = apigw.LambdaRestApi(
            self,
            id="FilesApiGateway",
            rest_api_name="Files API",
            description="API Gateway for Files API",
            handler=files_api_lambda,
            proxy=False,  # Disable proxy integration to define custom resources
            deploy=True,  # Enable automatic deployment when the API is created
            binary_media_types=["*/*"],  # Allow binary media types to access Fastapi docs page & other binary content
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                tracing_enabled=True,
                metrics_enabled=True,
                # API Gateway Execution Logs: it is recommended to turn it off in production
                # Execution logs capture detailed information about API request processing lifecycle. It should be
                # enabled only for debugging purposes as it can quite verbose and incur additional cloudwatch costs and may expose sensitive information.
                # AWS auto creates a log group for execution logs with format: API-Gateway-Execution-Logs/{rest-api-id}/{stage-name}
                logging_level=None,  # apigw.MethodLoggingLevel.INFO,  # Set to INFO or ERROR to enable execution logging
                # Access Logs: Access logs capture traffic-related information about the requests coming into API Gateway.
                access_log_destination=apigw.LogGroupLogDestination(log_group=api_gw_access_log_group_prod),
                # access_log_format=apigw.AccessLogFormat.clf(),  # Common Log Format for access logs
                # access_log_format=apigw.AccessLogFormat.json_with_standard_fields(...)    # Pre-defined JSON format with standard fields
                access_log_format=apigw_custom_access_log_format(),  # Custom JSON format for access logs
            ),
            # Setting cloudWatchRole to true ensures CDK creates the necessary IAM role for logging
            cloud_watch_role=True,
            cloud_watch_role_removal_policy=cdk.RemovalPolicy.DESTROY,
            # endpoint_configuration=apigw.EndpointConfiguration(
            #     types=[apigw.EndpointType.REGIONAL],  # Use REGIONAL endpoint type for cost-effectiveness
            # ),
            endpoint_types=[
                apigw.EndpointType.REGIONAL
            ],  # Default is EDGE-OPTIMIZED, but REGIONAL is more cost-effective for most use cases
        )
        # Add methods to the root resource
        files_api_gw.root.add_method("GET")  # To access the OpenAPI docs page at root path
        files_api_gw.root.add_resource("{proxy+}").add_method("ANY")

        # Print out the API Gateway URL, S3 bucket URL, and Lambda function Url
        cdk.CfnOutput(
            self,
            id="FilesApiBucketConsoleURL",
            value=f"https://s3.console.aws.amazon.com/s3/buckets/{files_api_bucket.bucket_name}",
            description="Files API S3 Bucket Console URL",
        )
        cdk.CfnOutput(
            self,
            id="FilesApiLambdaFunctionConsoleURL",
            value=f"https://{self.region}.console.aws.amazon.com/lambda/home?region={self.region}#/functions/{files_api_lambda.function_name}",
            description="Files API Lambda Function Console URL",
        )
        cdk.CfnOutput(
            self,
            id="FilesApiGatewayConsoleURL",
            value=f"https://{self.region}.console.aws.amazon.com/apigateway/home?region={self.region}#/apis/{files_api_gw.rest_api_id}/stages/prod",
            description="Files API Gateway Console URL",
        )
        # By default, the API Gateway URL is printed to the console output
        # cdk.CfnOutput(
        #     self,
        #     id="FilesApiGatewayUrl",
        #     value=files_api_gw.url,
        #     description="Files-API API Gateway Invoke URL",
        # )

        # Print an output saying manually create the SSM SecureString parameter
        cdk.CfnOutput(
            self,
            id="ManualSSMParameterCreationNotice",
            value="Please remember to manually create a SecureString parameter in AWS SSM Parameter Store with name"
            " '/files-api/openai-api-key' with your OpenAI API Key after the first deployment of this stack.\n"
            f"You can create it here: https://{self.region}.console.aws.amazon.com/systems-manager/parameters/",
            description="Manual SSM Parameter Creation Notice",
        )


def apigw_custom_access_log_format() -> apigw.AccessLogFormat:
    """
    Custom API Gateway Access Log Format based on Alex DeBrie's blog post.

    Ref:
    - Alex DeBrie's blog post: https://www.alexdebrie.com/posts/api-gateway-access-logs/#access-logging-fields
    - My article: https://ericriddoch.notion.site/Deep-Dive-Log-Correlation-Setting-up-Access-and-Execution-Logs-in-our-API-19a29335f6d880149ec2e1875e8b8761?pvs=143
    """
    # ref: Refer to Alex DeBrie's blog post for custom access log format:
    return apigw.AccessLogFormat.custom(
        json.dumps(
            {  # Request Information
                "requestTime": apigw.AccessLogField.context_request_time(),
                "requestId": apigw.AccessLogField.context_request_id(),
                # There is slight difference in requestId & extendedRequestId: Clients can override the requestID
                # but not the extendedRequestId, which may be helpful for troubleshooting & debugging purposes
                "extendedRequestId": apigw.AccessLogField.context_extended_request_id(),
                "httpMethod": apigw.AccessLogField.context_http_method(),
                "path": apigw.AccessLogField.context_path(),
                "resourcePath": apigw.AccessLogField.context_resource_path(),
                "status": apigw.AccessLogField.context_status(),
                "responseLatency": apigw.AccessLogField.context_response_latency(),  # in milliseconds
                "xrayTraceId": apigw.AccessLogField.context_xray_trace_id(),
                # Integration Information
                # AWS Endpoint Request ID: The requestID generated by Lambda function invocation
                # "integrationRequestId": apigw.AccessLogField.context_integration_request_id,
                "integrationRequestId": "$context.integration.requestId",
                # Integration Response Status Code: Status code returned by the AWS Lambda function
                "functionResponseStatus": apigw.AccessLogField.context_integration_status(),
                # Latency of the integration, like Lambda function, in milliseconds
                "integrationLatency": apigw.AccessLogField.context_integration_latency(),
                # Status code returned by the AWS Lambda Service and not the backend Lambda function code
                "integrationServiceStatus": apigw.AccessLogField.context_integration_status(),
                # User Identity Information
                "ip": apigw.AccessLogField.context_identity_source_ip(),
                "userAgent": apigw.AccessLogField.context_identity_user_agent(),
            }
        ),
    )


###############
# --- App --- #
###############

# CDK App
app = cdk.App()

cdk.Tags.of(app).add("x-project", "files-api")
cdk.Tags.of(app).add("x-owner", "mlops-club-amit")

FilesApiCdkStack(
    app,
    "FilesApiCdkStack",
    # If you don't specify 'env', this stack will be environment-agnostic.
    # Account/Region-dependent features and context lookups will not work,
    # but a single synthesized template can be deployed anywhere.
    # Uncomment the next line to specialize this stack for the AWS Account
    # and Region that are implied by the current CLI configuration.
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
    # Uncomment the next line if you know exactly what Account and Region you
    # want to deploy the stack to. */
    # env=cdk.Environment(account='123456789012', region='us-east-1'),
    # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
)

app.synth()
