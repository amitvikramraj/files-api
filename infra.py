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
    aws_cognito as cognito,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
    aws_ssm as ssm,
)
from constructs import Construct

THIS_DIR = Path(__file__).parent

S3_BUCKET_NAME = os.environ["S3_BUCKET_NAME"]
API_GATEWAY_STAGE_NAME = "prod"
COGNITO_DOMAIN_UNIQUE_PREFIX = "avr-files-api"  # unique prefix for the Cognito domain

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
        ssm_openai_api_secret_key = query_secure_string_ssm_parameter(
            self, id="ExistingOpenAIApiSecretKey", parameter_name="/files-api/openai-api-key", version=1
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
                ).hexdigest(),
                # ^^^Custom hash based on dependency files
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
                exclude=_assets_to_exclude,
                ignore_mode=cdk.IgnoreMode.GLOB,
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
                ## OpenAI API Key configuration
                # "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
                # "OPENAI_API_SECRET_NAME": openai_api_secret_key.secret_name,
                "OPENAI_API_SSM_PARAMETER_NAME": ssm_openai_api_secret_key.parameter_name,
                ## AWS Parameters and Secrets Lambda Extension configuration
                # You can find all the supported environment variables here:
                # https://docs.aws.amazon.com/lambda/latest/dg/with-secrets-manager.html
                "PARAMETERS_SECRETS_EXTENSION_HTTP_PORT": "2773",
                # ^^^Port on which the AWS Parameters and Secrets Lambda Extension listens by default
                "PARAMETERS_SECRETS_EXTENSION_CACHE_ENABLED": "TRUE",
                # Enable caching of secrets to reduce latency and cost
                "SECRETS_MANAGER_TTL": "300",  # Cache secrets for 300 seconds, Time-to-live for cached secrets.
                ## Cognito configuration - Needed when Cognito is enabled
                # "COGNITO_ENABLED": "true",
                # "COGNITO_DOMAIN": "<replace-with-actual-cognito-domain-from-cdk-output>",
                # "COGNITO_USER_POOL_CLIENT_ID": "<replace-with-actual-cognito-user-pool-client-id-from-cdk-output>",
            },
        )

        # Grant the Lambda function permissions to:
        # - read/write to the S3 bucket
        # - read the OpenAI API Key secret from SSM Parameter Store
        # - write logs to CloudWatch Logs
        files_api_bucket.grant_read_write(files_api_lambda)
        ssm_openai_api_secret_key.grant_read(files_api_lambda)
        files_api_lambda_log_group.grant_write(files_api_lambda)

        # Setup API Gateway with resources and methods
        files_api_gw = define_lambda_rest_api(
            scope=self,
            id="FilesApiGateway",
            rest_api_name="Files API",
            description="API Gateway for Files API Lambda Function",
            handler=files_api_lambda,
        )
        setup_api_routes_and_methods_without_authorizer(api_gw=files_api_gw)
        # ^^^Comment this out if you want to enable Cognito

        # UNCOMMENT BELOW CODE TO ENABLE COGNITO - Also make sure to uncomment the env vars in Lambda Function defined above
        # # Setup Cognito User Pool
        # # (must not depend on API Gateway to avoid circular dependency)

        # # fmt: off
        # # Since the REST API ID is a dynamic value known only after the API is created, we use Fn.join to construct the API base URL.
        # api_base_url = cdk.Fn.join(
        #     "",
        #     ["https://", files_api_gw.rest_api_id, ".execute-api.", cdk.Aws.REGION, ".", cdk.Aws.URL_SUFFIX, "/", API_GATEWAY_STAGE_NAME],
        # )
        # # fmt: on

        # user_pool, user_pool_client = setup_cognito(
        #     scope=self,
        #     id="FilesApiCognitoUserPool",
        #     user_pool_name="files-api-user-pool",
        #     api_gw_url=api_base_url,
        # )

        # # Cognito User Pools Authorizer for the API Gateway
        # files_api_gw_authorizer = apigw.CognitoUserPoolsAuthorizer(
        #     self,
        #     id="FilesApiGatewayAuthorizer",
        #     cognito_user_pools=[user_pool],
        #     authorizer_name="files-api-gw-cognito-authorizer",
        #     results_cache_ttl=cdk.Duration.minutes(15),  # max value can be 1 hour
        # )
        # # Setup API routes and methods with Cognito Authorizer
        # setup_api_routes_and_methods_with_cognito_authorizer(
        #     api_gw=files_api_gw,
        #     authorizer=files_api_gw_authorizer,
        # )

        # Print out the API Gateway URL, S3 bucket URL, and Lambda function Url
        cdk.CfnOutput(
            self,
            id="FilesApiBucketConsoleURL",
            value=f"https://s3.console.aws.amazon.com/s3/buckets/{files_api_bucket.bucket_name}\n",
            description="Files API S3 Bucket Console URL",
        )
        cdk.CfnOutput(
            self,
            id="FilesApiLambdaFunctionConsoleURL",
            value=f"https://{self.region}.console.aws.amazon.com/lambda/home?region={self.region}#/functions/{files_api_lambda.function_name}\n",
            description="Files API Lambda Function Console URL",
        )
        cdk.CfnOutput(
            self,
            id="FilesApiGatewayConsoleURL",
            value=f"https://{self.region}.console.aws.amazon.com/apigateway/home?region={self.region}#/apis/{files_api_gw.rest_api_id}/stages/{API_GATEWAY_STAGE_NAME}\n",
            description="Files API Gateway Console URL",
        )
        cdk.CfnOutput(
            self,
            id="CognitoDomain",
            value=f"{COGNITO_DOMAIN_UNIQUE_PREFIX}.auth.{self.region}.amazoncognito.com\n",
            description="Cognito Domain",
        )

        # Print an output saying manually create the SSM SecureString parameter
        cdk.CfnOutput(
            self,
            id="ManualSSMParameterCreationNotice",
            value="\nPlease remember to manually create a SecureString parameter in AWS SSM Parameter Store with name"
            " '/files-api/openai-api-key' with your OpenAI API Key after the first deployment of this stack."
            f"You can create it here: https://{self.region}.console.aws.amazon.com/systems-manager/parameters/",
            description="Manual SSM Parameter Creation Notice",
        )

        # cdk.CfnOutput(
        #     self,
        #     id="ManualCognitoDomainAndUserPoolClientIdEnvironmentVariablesSettingNotice",
        #     value="\nManually set the Cognito Domain and User Pool Client ID as Lambda Env Vars in the Lambda Console with following keys and values:"
        #     f"\n\nCOGNITO_DOMAIN: {COGNITO_DOMAIN_UNIQUE_PREFIX}.auth.{self.region}.amazoncognito.com\n"
        #     f"COGNITO_USER_POOL_CLIENT_ID: {user_pool_client.user_pool_client_id}\n",
        #     description="Manual Cognito Domain and User Pool Client ID Environment Variables Setting Notice",
        # )


def setup_api_routes_and_methods_without_authorizer(api_gw: apigw.LambdaRestApi) -> None:
    """
    Setup Public routes without any auth to access the OpenAPI docs page and other API endpoints.

    - GET / (the root path with GET method to access the OpenAPI docs page)
    - ANY /{proxy+} (the proxy path to allow all subpaths under / paths)
    """
    # Add methods to the root resource
    api_gw.root.add_method("GET", authorization_type=apigw.AuthorizationType.NONE)
    # ^^^To access the OpenAPI docs page at root path
    api_gw.root.add_resource("{proxy+}").add_method("ANY")


def setup_api_routes_and_methods_with_cognito_authorizer(
    api_gw: apigw.LambdaRestApi,
    authorizer: apigw.CognitoUserPoolsAuthorizer,
) -> None:
    """
    Setup API routes and methods with Cognito Authorizer.

    This creates:
    - Public Routes without any auth to access the OpenAPI docs page:
      - GET / (the root path with GET method to access the OpenAPI docs page)
      - GET /openapi.json (the OpenAPI schema to reterive the OpenAPI schema)
      - /docs (Adds a /docs resource primarily for the Oauth2 Redirect)
      - GET /docs/oauth2-redirect (the oauth2 redirect helper page to handle the oauth2 redirect)
    - Private Routes with Cognito Auth:
      - /api (the base path under which all the private Files API endpoints are protected)
      - /api/{proxy+} (the proxy path to allow all subpaths under /api/* paths)
    """
    # Add methods to the root resource
    api_gw.root.add_method("GET", authorization_type=apigw.AuthorizationType.NONE)

    # Public: OpenAPI schema
    openapi = api_gw.root.add_resource("openapi.json")
    openapi.add_method("GET", authorization_type=apigw.AuthorizationType.NONE)

    # Public: Swagger oauth redirect helper page
    docs = api_gw.root.add_resource("docs")
    oauth2_redirect = docs.add_resource("oauth2-redirect")
    oauth2_redirect.add_method("GET", authorization_type=apigw.AuthorizationType.NONE)

    cognito_method_scopes = ["openid", "email", "profile"]
    # ^^^OAuth scopes on the method make API Gateway accept *access* tokens (and validate scopes).
    # Without these, API Gateway treats the token as an ID token only.

    # Private API Routes for the Files API Endpoints: Protect base path & proxy path.
    # "/api" base path under which all the private Files API endpoints are protected.
    api = api_gw.root.add_resource("api")
    api.add_method(
        "ANY",
        authorization_type=apigw.AuthorizationType.COGNITO,
        authorizer=authorizer,
        authorization_scopes=cognito_method_scopes,
    )

    # Protect /api/{proxy+} (proxy path to allow all subpaths under /api/* paths).
    api_proxy = api.add_resource("{proxy+}")
    api_proxy.add_method(
        "ANY",
        authorization_type=apigw.AuthorizationType.COGNITO,
        authorizer=authorizer,
        authorization_scopes=cognito_method_scopes,
    )

    # api.add_cors_preflight(
    #     allow_origins=apigw.Cors.ALL_ORIGINS,
    #     allow_methods=apigw.Cors.ALL_METHODS,
    #     allow_headers=["Authorization", "Content-Type", "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token"],
    # )

    # api_proxy.add_cors_preflight(
    #     allow_origins=apigw.Cors.ALL_ORIGINS,
    #     allow_methods=apigw.Cors.ALL_METHODS,
    #     allow_headers=["Authorization", "Content-Type", "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token"],
    # )


def define_lambda_rest_api(
    scope: Construct, id: str, rest_api_name: str, description: str, handler: _lambda.Function
) -> apigw.LambdaRestApi:
    """
    Define a Lambda REST API(API Gateway) with custom access log group enabled.

    Args:
        scope: The scope of the CDK Stack.
        id: The id of the API Gateway.
        rest_api_name: The name of the API Gateway.
        description: The description of the API Gateway.
        handler: The Lambda function to handle the API Gateway requests.

    Returns:
        The defined API Gateway.

    """
    # Log group for API Gateway access logs
    api_gw_access_log_group_prod = logs.LogGroup(
        scope=scope,
        id=f"{id}AccessLogGroup",
        log_group_name=f"/aws/apigateway/access-logs/{rest_api_name}/{API_GATEWAY_STAGE_NAME}",
        retention=logs.RetentionDays.ONE_MONTH,
        removal_policy=cdk.RemovalPolicy.DESTROY,
    )

    # The LambdaRestApi L2 construct by default creates a `test-invoke-stage` stage for the API

    # I disabled the proxy integration(proxy=False) because on the root path it defines "ANY" method by default which we do not want.
    # For the root path we only want to allow "GET" method to access the OpenAPI docs page.
    api_gw = apigw.LambdaRestApi(
        scope=scope,
        id=id,
        rest_api_name=rest_api_name,
        description=description,
        handler=handler,
        proxy=False,  # Disable proxy integration to define custom resources
        deploy=True,  # Enable automatic deployment when the API is created
        binary_media_types=["*/*"],  # Allow binary media types to access Fastapi docs page & other binary content
        # deploy_options: Options for the API Gateway stage that will always point to the latest deployment when deploy is enabled
        deploy_options=apigw.StageOptions(
            stage_name=API_GATEWAY_STAGE_NAME,
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
        endpoint_types=[apigw.EndpointType.REGIONAL],
        # ^^^Default is EDGE-OPTIMIZED, but REGIONAL is more cost-effective for most use cases
        endpoint_export_name=f"{id}Endpoint",
        # ^^^Used as CfnOutput export name for the API Gateway endpoint URL.
    )
    return api_gw


def setup_cognito(
    scope: Construct,
    id: str,
    user_pool_name: str,
    *,
    api_gw_url: str,
) -> tuple[cognito.UserPool, cognito.UserPoolClient]:
    # Define cognito user pool
    user_pool = configure_cognito_user_pool(scope=scope, id=id, user_pool_name=user_pool_name)

    # Enable hosted UI for the user pool, Create a Domain for the Hosted UI
    # Adding a domain to a User Pool will also automatically enable an oAuth2 authorization server,
    # with a couple of useful REST API endpoints.
    # ref: https://docs.aws.amazon.com/cognito/latest/developerguide/managed-login-endpoints.html
    user_pool.add_domain(
        id=f"{id}Domain",
        cognito_domain=cognito.CognitoDomainOptions(domain_prefix=COGNITO_DOMAIN_UNIQUE_PREFIX),
    )
    # ^^^The hosted UI is accessible at https://${uniquePrefix}.auth.${region}.amazoncognito.com.
    # ref: https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-assign-domain-prefix.html

    # Set Up Google OAuth Provider and register it with the user pool.
    google_provider = configure_google_oauth_provider(scope=scope, user_pool=user_pool)
    user_pool.register_identity_provider(provider=google_provider)
    # ^^^Register the Google provider with the user pool.
    # A User Pool can have multiple identity providers (Google, Facebook, SAML, etc.). So you need to explicitly
    # register the provider with the user pool. So when a user opens the Hosted UI (or your app) and clicks
    # "Sign in with Google", the User Pool looks at its registered identity providers, finds Google, and uses the
    # Google provider config to run the authentication flow with Google.

    # configure user pool with authentication flows for the users to sign in into the application
    user_pool_client = user_pool.add_client(
        id=f"{id}Client",
        user_pool_client_name="files-api-user-pool-client",
        supported_identity_providers=[
            cognito.UserPoolClientIdentityProvider.COGNITO,
            cognito.UserPoolClientIdentityProvider.GOOGLE,
        ],
        o_auth=cognito.OAuthSettings(
            flows=cognito.OAuthFlows(implicit_code_grant=False, authorization_code_grant=True),
            scopes=[cognito.OAuthScope.EMAIL, cognito.OAuthScope.OPENID, cognito.OAuthScope.PROFILE],
            default_redirect_uri=None,
            # After sign-in/sign-out, Cognito redirects the browser to these URLs (must match exactly).
            callback_urls=[f"{api_gw_url.rstrip('/')}/docs/oauth2-redirect"],
            logout_urls=[f"{api_gw_url.rstrip('/')}/"],
        ),
        auth_flows=cognito.AuthFlow(
            user=True,  # Enable Choice-based authentication.
            user_password=True,  # Enable auth using username & password.
        ),
        # ^^^Auth Flows: https://docs.aws.amazon.com/cognito/latest/developerguide/authentication.html
    )

    # Explicitly add the Google provider to the client's supported providers list if not done implicitly
    user_pool_client.node.add_dependency(google_provider)

    return user_pool, user_pool_client


def configure_cognito_user_pool(scope: Construct, id: str, user_pool_name: str) -> cognito.UserPool:
    """
    Configure a Cognito User Pool.

    Args:
        scope: The scope of the CDK Stack.
        id: The id of the Cognito User Pool.
        user_pool_name: The name of the Cognito User Pool.

    Returns:
        The configured user pool.

    """
    user_pool = cognito.UserPool(
        scope=scope,
        id=id,
        user_pool_name=user_pool_name,
        removal_policy=cdk.RemovalPolicy.DESTROY,
        # User Pool Configuration
        ## Feature Plan:
        feature_plan=cognito.FeaturePlan.ESSENTIALS,  # Cognito has 3 feature plans: LITE, ESSENTIALS, PLUS.
        # ^^^ref: https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-sign-in-feature-plans.html
        ## Sign-up Options for Users:
        self_sign_up_enabled=True,  # allow users to sign up themselves
        user_verification=cognito.UserVerificationConfig(
            email_subject="Verify your email",
            email_body="Thank you for signing up for Files API! Your verification code is: {####}",
            email_style=cognito.VerificationEmailStyle.CODE,
        ),
        # User can get invited by an admin to sign up
        user_invitation=cognito.UserInvitationConfig(
            email_subject="You are invited to sign up for Files API",
            email_body="Hello {username}! You have been invited to sign up for Files API. Your temporary password is: {####}",
        ),
        ## Sign-in Options:
        # Users registering or signing in into your application can do so with multiple identifiers.
        sign_in_aliases=cognito.SignInAliases(
            email=True,
            username=True,
            preferred_username=True,
        ),
        auto_verify={"email": True, "phone": False},
        # ^^^Cognito recommends that email and phone number be automatically verified. CDK does this by default.
        sign_in_case_sensitive=False,
        # ^^^ case insensitive is preferred in most situations, i.e. "user@example.com" & "User@example.com" are the same;
        # "my-username" & "My-Username" are the same. The case sensitivity cannot be changed once a user pool is created.
        ## Sign-in Policy: – Supported for ESSENTIALS or higher feature plans.
        # If sign-in policy is set, then you must also configure the user pool client with USER_AUTH authentication flow allowed
        sign_in_policy=cognito.SignInPolicy(
            # allowed_first_auth_factors=cognito.AllowedFirstAuthFactors()
            allowed_first_auth_factors={
                "password": True,  # password authentication must be enabled
                "email_otp": True,  # enables email message one-time password
                # "passkey": True,  # enables passkey sign-in
                # "sms_otp": True,   # enables SMS message one-time password
            },
        ),
        # Attributes represent the various properties of each user that's collected and stored in the user pool.
        # Note: Mutability of existing attributes cannot be changed via CloudFormation after the pool is created.
        standard_attributes=cognito.StandardAttributes(
            fullname={"required": True, "mutable": True},
            email={"required": True, "mutable": True},
            # phone_number={"required": False, "mutable": False},
        ),
        custom_attributes={"joined_on": cognito.DateTimeAttribute(mutable=False)},
        ## Attribute Verification:
        # When user updates attributes like email and phone number, Cognito marks it unverified until they verify the new value.
        # You can’t send messages to an unverified email address or phone number. Your user can’t sign in with an unverified alias attribute.
        # So we keep the original value of email and phone number until the user verifies the new value.
        keep_original=cognito.KeepOriginalAttrs(email=True, phone=None),
        ## Password Policy
        password_policy=cognito.PasswordPolicy(
            min_length=8,
            require_lowercase=True,
            require_uppercase=True,
            require_digits=True,
            require_symbols=True,
            temp_password_validity=cdk.Duration.days(1),
            # ^^^ tempPasswordValidity can be specified only in whole days. Specifying fractional days would throw an error.
        ),
        account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
    )

    return user_pool


def configure_google_oauth_provider(scope: Construct, user_pool: cognito.UserPool):
    """
    Configure Google OAuth2.0 for authentication.

    Creating a Google Identity Provider means, you give Cognito the configurations and credentials it needs to
    run the OAuth flow with Google.

    You are not defining "what Google is allowed to use" on Google's side.
    That's done in Google Cloud Console (scopes, redirect URIs, etc.).

    You are telling Cognito: "When a user chooses 'Sign in with Google', use this Google Client ID and Client Secret to:
    - Redirect the user to Google,
    - Receive the callback from Google (authorization code),
    - Exchange it for tokens and user info from Google,
    - Then create or link a user in my User Pool and issue my (Cognito) tokens.

    Args:
        scope: The scope of the CDK Stack.
        user_pool: The user pool to configure the Google OAuth2.0 for authentication.

    Returns:
        The configured Google OAuth2.0 provider.

    """
    # # Setting up Google OAuth2.0 for authentication
    # google_client_id = query_secure_string_ssm_parameter(
    #     scope, id="GoogleClientId", parameter_name="/files-api/google-client-id"
    # )
    # google_client_secret = query_secure_string_ssm_parameter(
    #     scope, id="GoogleClientSecret", parameter_name="/files-api/google-client-secret"
    # )
    google_client_secret = create_secrets_manager_secret(
        scope,
        id="GoogleClientSecret",
        secret_name="/files-api/google-client-secret",
        description="Google Client Secret for Files API",
    )
    google_provider = cognito.UserPoolIdentityProviderGoogle(
        scope=scope,
        id="GoogleOAuthProvider",
        # client_id=google_client_id.string_value,
        client_id="260340866171-j5jbd8992k06hrs8vj9m7pus4rr90724.apps.googleusercontent.com",
        # client_secret=google_client_secret.string_value,
        # string value is deprecated, instead it expects a SecretValue object. this is forcing you to use Secrets Manager.
        # client_secret_value=cdk.SecretValue.ssm_secure(parameter_name="/files-api/google-client-secret"),
        client_secret_value=google_client_secret.secret_value,
        scopes=["email", "profile", "openid"],
        user_pool=user_pool,
        # Mapping attributes from the identity provider to standard and custom attributes of the user pool.
        attribute_mapping=cognito.AttributeMapping(
            fullname=cognito.ProviderAttribute.GOOGLE_NAME,
            email=cognito.ProviderAttribute.GOOGLE_EMAIL,
            email_verified=cognito.ProviderAttribute.GOOGLE_EMAIL_VERIFIED,
        ),
    )
    google_provider.apply_removal_policy(cdk.RemovalPolicy.DESTROY)
    return google_provider


def query_secure_string_ssm_parameter(
    scope: Construct, id: str, parameter_name: str, version: int = 1
) -> ssm.IStringParameter:
    """
    Query a SecureString SSM parameter from Parameter Store.

    Args:
        scope: The scope of the CDK Stack.
        id: The id of the SSM parameter.
        parameter_name: The name of the SSM parameter.
        version: The version of the SSM parameter.

    Returns:
        The SecureString SSM parameter.

    """
    return ssm.StringParameter.from_secure_string_parameter_attributes(
        scope=scope,
        id=id,
        parameter_name=parameter_name,
        version=version,
    )


def create_secrets_manager_secret(
    scope: Construct,
    id: str,
    secret_name: str,
    description: str,
) -> secretsmanager.Secret:
    """
    Create a Secrets Manager secret.

    Args:
        scope: The scope of the CDK Stack.
        id: The id of the Secrets Manager secret.
        secret_name: The name of the Secrets Manager secret.
        description: The description of the Secrets Manager secret.

    Returns:
        The created Secrets Manager secret.

    """
    secret = secretsmanager.Secret(
        scope=scope,
        id=id,
        secret_name=secret_name,
        description=description,
        # secret_string_value=cdk.SecretValue.ssm_secure(parameter_name="/files-api/google-client-secret"),
        # ^^^AWS discourages to pass the secret value directly in the CDK code as the value will be included in the
        # output of the cdk as part of synthesis, and will appear in the CloudFormation template in the console
        removal_policy=cdk.RemovalPolicy.DESTROY,
    )
    # ^^^The recommended way is to leave this field empty and manually add the secret value in the Secrets Manager console after deploying the stack.
    # AWS Secrets Manager will automatically create a placeholder/empty secret for you
    # The secret exists in AWS, but initially has no value (or a generated random value depending on the context).

    # This way, the secret value never appears in code, outputs, or CloudFormation templates.

    return secret


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

cdk.Tags.of(app).add("x-owner", "amit")
cdk.Tags.of(app).add("x-project", "files-api")

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
