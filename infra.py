import os
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_apigateway as apigw,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

THIS_DIR = Path(__file__).parent

S3_BUCKET_NAME = os.environ["S3_BUCKET_NAME"]


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
        openai_api_secret_key = secretsmanager.Secret(
            self,
            id="OpenAIApiSecretKey",
            description="OpenAI API Key to generate text, images, and audio using OpenAI's API",
            secret_name="files-api/openai-api-key",
            # secret_string_value=...,
            # ^^^AWS discourages to pass the secret value directly in the CDK code as the value will be included in the
            # output of the cdk as part of synthesis, and will appear in the CloudFormation template in the console
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        # ^^^The recommended way is to leave this field empty and manually add the secret value in the Secrets Manager console after deploying the stack.
        # AWS Secrets Manager will automatically create a placeholder/empty secret for you
        # The secret exists in AWS, but initially has no value (or a generated random value depending on the context).

        # This way, the secret value never appears in code, outputs, or CloudFormation templates.

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
                bundling={
                    "image": _lambda.Runtime.PYTHON_3_12.bundling_image,
                    "command": [
                        "bash",
                        "-c",
                        # 0. Upgrade pip to the latest version
                        "pip install --upgrade pip && "
                        # 1. Install uv
                        "pip install uv && "
                        # 2. Use uv to install the 'aws-lambda' group into /asset-output/python
                        "uv pip install --editable . --group aws-lambda --target /asset-output/python",
                    ],
                    "user": "root",  # `user` override to be able to install uv and upgrade pip
                },
                exclude=["tests/*", ".venv", "*.pyc", "__pycache__", ".git"],
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
                exclude=["tests/*", ".venv", "*.pyc", "__pycache__", ".git"],
            ),
            layers=[files_api_lambda_layer, secrets_manager_lambda_extension_layer],
            tracing=_lambda.Tracing.ACTIVE,
            environment={
                "S3_BUCKET_NAME": files_api_bucket.bucket_name,
                "LOGURU_LEVEL": "DEBUG",
                "AWS_EMF_NAMESPACE": "files-api",
                "AWS_XRAY_TRACING_NAME": "Files API",
                "AWS_XRAY_DAEMON_CONTEXT_MISSING": "RUNTIME_ERROR",
                # "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
                "OPENAI_API_SECRET_NAME": openai_api_secret_key.secret_name,
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

        # Grant the Lambda function permissions to read the OpenAI API Key secret
        openai_api_secret_key.grant_read(files_api_lambda)

        # Setup API Gateway with resources and methods

        # The LambdaRestApi construct by default creates a `test-invoke-stage` stage for the API

        # I disabled the proxy integration(proxy=False) because on the root path it defined "ANY" method by default which  we do not want.
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
            ),
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
        #     description="Files-API API Gateway URL",
        # )


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
