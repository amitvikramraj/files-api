Here's a learning path for CI/CD with AWS CDK:

## Core Concepts to Learn

**1. AWS CDK Fundamentals**
- CDK Pipelines construct
- Stacks vs Stages vs Applications
- CDK synthesis and bootstrapping
- Cross-account/cross-region deployments

**2. CI/CD Patterns**
- Pipeline stages: Source → Build → Test → Deploy
- Blue/Green and Canary deployments
- Self-mutating pipelines (pipelines that update themselves)
- Manual approval gates

**3. AWS Services Integration**
- CodePipeline, CodeBuild, CodeCommit
- GitHub Actions with OIDC for AWS
- AWS Secrets Manager for credentials
- CloudWatch for monitoring pipeline metrics

**4. Testing Strategies**
- CDK assertions and snapshot testing
- Integration tests in pipeline stages
- Security scanning (cdk-nag)
- Infrastructure validation pre-deployment

## Recommended Resources

**Official AWS Documentation:**
- [CDK Pipelines Documentation](https://docs.aws.amazon.com/cdk/v2/guide/cdk_pipeline.html)
- [CDK Workshop - CI/CD Module](https://cdkworkshop.com/)
- [AWS CDK Examples - Pipelines](https://github.com/aws-samples/aws-cdk-examples)

**Video Courses:**
- AWS re:Invent sessions on "CDK Pipelines" (YouTube)
- A Cloud Guru / Pluralsight CDK courses

**Hands-On:**
- [CDK Patterns - CI/CD Patterns](https://cdkpatterns.com/)
- AWS Well-Architected Labs for CI/CD

**GitHub Actions specific:**
- [AWS Actions for GitHub](https://github.com/aws-actions)
- [Configure AWS Credentials Action](https://github.com/aws-actions/configure-aws-credentials)

**Best Practices:**
- AWS Well-Architected Framework - Operational Excellence Pillar
- CDK Best Practices guide

Start with the official CDK Pipelines documentation, then work through a hands-on tutorial to deploy your files-api project through a pipeline.