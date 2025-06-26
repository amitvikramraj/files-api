from pathlib import Path

import aws_cdk as cdk
from aws_cdk import Stack, aws_apigateway as apigw, aws_lambda as _lambda, aws_s3 as s3
from constructs import Construct

THIS_DIR = Path(__file__).parent


class FilesApiCdkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create an S3 bucket
        files_api_bucket = s3.Bucket(
            self,
            id="FilesApiBucket",
            bucket_name=f"files-api-bucket-{self.account}",
            auto_delete_objects=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Create a Lambda function & Lambda Layer
        files_api_lambda_layer = _lambda.LayerVersion(
            self,
            id="FilesApiLambdaLayer",
            layer_version_name="files-api-layer",
            description="Lambda layer for Files API",
            compatible_architectures=[_lambda.Architecture.ARM_64],
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            code=_lambda.Code.from_asset(
                path=(THIS_DIR / "../../../files-api").as_posix(),
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
                path=(THIS_DIR / "../../../files-api/src").as_posix(),
                exclude=["tests/*", ".venv", "*.pyc", "__pycache__", ".git"],
            ),
            layers=[files_api_lambda_layer],
            tracing=_lambda.Tracing.ACTIVE,
            environment={
                "S3_BUCKET_NAME": files_api_bucket.bucket_name,
                "LOGURU_LEVEL": "DEBUG",
                "AWS_EMF_NAMESPACE": "files-api",
                "AWS_XRAY_TRACING_NAME": "Files API",
                "AWS_XRAY_DAEMON_CONTEXT_MISSING": "RUNTIME_ERROR",
            },
        )

        # Grant the Lambda function permissions to read/write to the S3 bucket
        files_api_bucket.grant_read_write(files_api_lambda)

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
