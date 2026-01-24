Optimizing tool selection...Looking at your infra.py, I can see you have a basic Lambda REST API setup. Here are the key production patterns and concepts you should learn:

## API Gateway Deployment Patterns to Study

**1. API Types & When to Use Them**
- REST API vs HTTP API (cost/feature tradeoffs)
- WebSocket APIs for real-time communication
- Regional vs Edge-Optimized vs Private endpoints

**2. Authentication & Authorization**
- IAM authorization
- Lambda authorizers (custom auth logic)
- Cognito User Pools integration
- API Keys and Usage Plans
- OAuth 2.0 / JWT validation

**3. Traffic Management**
- Throttling and rate limiting (per-client quotas)
- Usage plans for different customer tiers
- API Keys management
- Request/Response validation

**4. Deployment Strategies**
- Stage variables for environment configuration
- Canary deployments (gradual traffic shifting)
- Multiple stages (dev/staging/prod)
- Stage-specific configuration

**5. Observability & Monitoring**
- CloudWatch Logs (access logs vs execution logs)
- X-Ray tracing integration (you have this!)
- Custom CloudWatch metrics
- Alarms for error rates and latency

**6. Cost Optimization**
- Caching strategies at API Gateway level
- Regional vs Edge endpoints
- HTTP API vs REST API cost comparison

**7. Security Best Practices**
- WAF (Web Application Firewall) integration
- Resource policies to restrict access
- TLS/SSL certificate management
- CORS configuration
- Request validation to block malformed requests

**8. Domain & DNS**
- Custom domain names
- Certificate management (ACM)
- Base path mappings
- API versioning strategies

## Recommended Resources

**AWS Documentation:**
- [API Gateway Best Practices](https://docs.aws.amazon.com/apigateway/latest/developerguide/best-practices.html)
- [Choosing Between HTTP and REST APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html)
- [API Gateway Security Best Practices](https://docs.aws.amazon.com/apigateway/latest/developerguide/security-best-practices.html)

**Architecture Patterns:**
- [AWS Serverless Application Lens](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/) - comprehensive guide
- [API Gateway Deployment Best Practices whitepaper](https://aws.amazon.com/blogs/compute/best-practices-for-organizing-larger-serverless-applications/)

**CDK Specific:**
- [AWS CDK API Gateway L2 Constructs](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_apigateway-readme.html)
- CDK Patterns for API Gateway: https://github.com/cdk-patterns/serverless

**Hands-On Learning:**
- AWS Workshops: https://catalog.workshops.aws/
- Serverless Land: https://serverlessland.com/patterns?framework=CDK

**Key Topics for Your Current Setup:**
1. Add request/response validation models
2. Implement proper error responses with Gateway Responses
3. Add CloudWatch access logging
4. Consider usage plans if this is a public API
5. Implement custom domain with Route53
6. Add Lambda authorizer if you need custom auth

Start with the AWS Well-Architected Serverless Lens - it covers all five pillars (operational excellence, security, reliability, performance, cost) specifically for serverless applications.