# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "aws-cdk-lib>=2.233.0",
#     "constructs>=10.4.4",
# ]
# ///
"""Creating an IAM Role for GitHub OIDC to allow GitHub Actions to assume the role and deploy CDK stack."""

import os
import re

import aws_cdk as cdk
from aws_cdk import Stack, aws_iam as iam
from constructs import Construct

"""
Information on GitHub OIDC provider:

- official docs by GitHub: https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services
- where to find the GitHub Actions thumbprints for the OIDC provider: https://github.blog/changelog/2023-06-27-github-actions-update-on-oidc-integration-with-aws/
- video on setting this up: https://www.youtube.com/watch?v=USIVWqXVv_U
"""


class GitHubActionsOIDCRoleStack(Stack):
    """Stack to create an IAM Role for GitHub OIDC."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # # define parameter or context variable for GitHub repository name and owner for the cdk app
        # github_repo_parameter = cdk.CfnParameter(
        #     self,
        #     "GitHubRepo",
        #     type="String",
        #     description="GitHub repository name in the format 'owner/repo'. E.g., 'amitvraj/my-repo'",
        #     allowed_pattern=".+/.+",
        #     default=None,  # User must provide value
        # )

        # Use context variable for GitHub repository name and owner
        github_repo = self.node.try_get_context("github_repo")
        if not github_repo:
            raise ValueError("GitHub repository must be provided in the context in the format 'owner/repo'.")

        if github_repo:
            # Match the pattern 'owner/repo'
            if not re.match(r"^[^/]+/[^/]+$", github_repo):
                raise ValueError("GitHub repository must be in the format 'owner/repo'.")

        # Create a OIDC Provider resource if not already existing
        github_provider: iam.IOpenIdConnectProvider | iam.OidcProviderNative

        # Check if we should create a new OIDC provider or use an existing one
        create_oidc_provider_str = self.node.try_get_context("create_oidc_provider")

        # Context values from CLI are strings, so we need to check the string value
        if create_oidc_provider_str.lower() == "false":
            oidc_provider_arn = f"arn:aws:iam::{self.account}:oidc-provider/token.actions.githubusercontent.com"
            # Import existing OIDC provider
            # github_provider = iam.OpenIdConnectProvider.from_open_id_connect_provider_arn(
            #     self,
            #     id="GitHubOIDCProvider",
            #     open_id_connect_provider_arn=oidc_provider_arn,
            # )
        else:
            # Create a new OIDC provider - This can be ONLY ONE per AWS account
            github_provider = iam.OidcProviderNative(
                self,
                id="GitHubOIDCProvider",
                url="https://token.actions.githubusercontent.com",
                client_ids=["sts.amazonaws.com"],
                thumbprints=[
                    # https://github.blog/changelog/2023-06-27-github-actions-update-on-oidc-integration-with-aws/
                    "6938fd4d98bab03faadb97b34396831e3780aea1",
                    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
                ],
            )
            oidc_provider_arn = github_provider.oidc_provider_arn

        # Create the IAM Role for GitHub Actions OIDC
        github_oidc_role = iam.Role(
            self,
            "GitHubActionsOIDCRole",
            assumed_by=iam.FederatedPrincipal(
                # federated="arn:aws:iam::" + self.account + ":oidc-provider/token.actions.githubusercontent.com",
                federated=oidc_provider_arn,
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                    },
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": f"repo:{github_repo}:*",
                    },
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
            role_name="GitHubActionsOIDCRole",
            description="IAM Role for GitHub Actions to assume via OIDC for deploying CDK stack.",
        )

        # Attach necessary policies to the role (e.g., AdministratorAccess, PowerUserAccess, or custom policies)
        github_oidc_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("PowerUserAccess"))

        # Output the ARN of the IAM Role
        cdk.CfnOutput(
            self,
            "GitHubActionsOIDCRoleARNOutput",
            value=github_oidc_role.role_arn,
            description="ARN of the IAM Role for GitHub Actions OIDC",
        )


###############
# --- App --- #
###############

# CDK App
app = cdk.App()

cdk.Tags.of(app).add("x-project", "files-api")


GitHubActionsOIDCRoleStack(
    app,
    construct_id="GitHubActionsOIDCRoleStack",
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
