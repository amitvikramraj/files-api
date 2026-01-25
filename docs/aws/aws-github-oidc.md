# Setting up Authentication in GitHub Actions with OpendID Connect (OIDC) to deploy to AWS

Couple of things I want to cover:
- IAM 101
- What is Identity providers and what is Identity Federation in AWS?
- Where does OIDC fit in? and What is OIDC?
- How to setup OIDC between GitHub Actions and AWS?
- How OIDC authentication works in GitHub Actions to deploy to AWS?
- What is a WebIdentity Role?

## AWS IAM 101

AWS Identity and Access Management (IAM) helps you control who has access to your AWS resources (authentication) and what actions they can perform againts those resources (authorization). IAM provides the infrastructure necessary to control authentication and authorization for your AWS accounts.

**Identites:**
- A fresh AWS account has something called the "root user" which has complete access to the account.
- Using IAM, we can create "identities" that can represent a single user, groups of users(like admins, devs), or services that need access to our AWS account.

**Access Management:**
- Once the an indentity is created, we need to define how much control that identity has over our AWS resources and exactly what actions they can perform against those resources.


## Identity Providers and Identity Federation in AWS

An Identity Provider (IdP) is a ...


ref:
- This [offical docs](https://docs.github.com/en/actions/concepts/security/openid-connect) from github expalins how OpenID Connect works with GitHub Actions.

- This [docs](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws) explains how to configure OIDC in AWS for GitHub Actions.
  - I also wrote a [CDK script](../../github_oidc_infra.py) that automates the setup of OIDC between GitHub Actions and AWS using AWS CDK.

- This [AWS blog post](https://aws.amazon.com/blogs/security/use-iam-roles-to-connect-github-actions-to-actions-in-aws/) shows you step by step instructions to manually setup OIDC between GitHub Actions and AWS.

- This [video](https://www.youtube.com/watch?v=USIVWqXVv_U) walks you through the process of setting up OIDC between GitHub Actions and AWS.

- GitHub [official action](https://github.com/aws-actions/configure-aws-credentials) to configure AWS credentials using OIDC.

- Refer the AWS docs to learn more about IAM and Identity Providers/Identity Federation
    - https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction.html
    - https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers.html
    - https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_oidc.html
    - [OpenID Connect Official Page](https://openid.net/developers/how-connect-works/)