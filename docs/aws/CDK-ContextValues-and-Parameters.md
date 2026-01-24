## CDK Parameters vs Context Values

### CDK Parameters (`CfnParameter`)

**What they are:**
- CloudFormation parameters that prompt for values at **deployment time**
- Defined in your CDK code but values provided when running `cdk deploy`
- Part of the CloudFormation template itself

**Characteristics:**
- ✅ Can change values between deployments without changing code
- ✅ Interactive prompts during deployment
- ✅ Good for values that differ per deployment
- ❌ Can't use in synthesis-time logic (if statements, loops)
- ❌ Limited to CloudFormation types (String, Number, List, etc.)
- ❌ Can't be used to conditionally create resources

**Use when:**
- Value changes frequently between deployments
- Different operators need different values
- You want deployment-time flexibility
- Building reusable CloudFormation templates

**Example:** Database password, instance sizes that operators choose

---

### CDK Context Values

**What they are:**
- Configuration values available at **synthesis time** (when running `cdk synth`)
- Can be provided via CLI, `cdk.json`, or `cdk.context.json`
- Become hardcoded in the synthesized CloudFormation template

**Characteristics:**
- ✅ Available during synthesis - can use in if/else logic
- ✅ Can conditionally create/skip resources
- ✅ Can be any data type (strings, objects, arrays)
- ✅ Cached in `cdk.context.json` for consistency
- ❌ Require re-synthesis to change values
- ❌ Not visible in CloudFormation console

**How to provide:**
```bash
# Via CLI
cdk deploy -c github_repo=owner/repo

# Via cdk.json
{
  "context": {
    "github_repo": "owner/repo"
  }
}
```

**Use when:**
- Value is known at development time
- Need to use value in synthesis logic
- Building environment-specific stacks
- Value is configuration, not secret

**Example:** Environment names, feature flags, account IDs, repo names

---

## Key Differences

| Aspect | Parameters | Context |
|--------|-----------|---------|
| **When resolved** | Deploy time | Synth time |
| **Can use in if/else** | ❌ No | ✅ Yes |
| **Interactive prompts** | ✅ Yes | ❌ No |
| **Visible in CFN console** | ✅ Yes | ❌ No |
| **Change without re-synth** | ✅ Yes | ❌ No |
| **Conditionally create resources** | ❌ No | ✅ Yes |

---

## For Your GitHub Repo Name

**Recommendation: Use Context** 🎯

**Why:**
1. **Known at development time** - repo name doesn't change deployment-to-deployment
2. **Better DX** - No interactive prompts, can be in version control
3. **Simpler** - Can be in `cdk.json` or environment variable
4. **Validation** - Can validate format during synthesis, not deployment

**Current issue with your Parameter approach:**
```python
if not github_repo_parameter.value_as_string:
    raise ValueError(...)  # This won't work!
```
Parameters are **tokens** at synthesis time, so you can't check if they're empty. The check always passes, then fails at CloudFormation deployment with a cryptic error.

---

## Recommended Implementation Patterns

**Pattern 1: Context via cdk.json**
```python
github_repo = self.node.try_get_context("github_repo")
if not github_repo:
    raise ValueError("Context value 'github_repo' is required")
```

```json
// cdk.json
{
  "context": {
    "github_repo": "avr2002/files-api"
  }
}
```

**Pattern 2: Environment Variable**
```python
github_repo = os.environ.get("GITHUB_REPO")
if not github_repo:
    raise ValueError("GITHUB_REPO environment variable required")
```

**Pattern 3: CLI Context**
```bash
cdk deploy -c github_repo=avr2002/files-api
```

---

## When Parameters ARE Better

Use Parameters when you need:
- Operators to make runtime decisions (e.g., instance type selection)
- Different values for same template across accounts
- CloudFormation StackSets with different parameter values
- True infrastructure-as-a-template (not infrastructure-as-code)

Example: A reusable template deployed by multiple teams with their own values.

---

## Learning Resources

**Official Docs:**
- [CDK Context](https://docs.aws.amazon.com/cdk/v2/guide/context.html)
- [CDK Parameters](https://docs.aws.amazon.com/cdk/v2/guide/parameters.html)
- [CDK Best Practices - Parameters vs Context](https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html#best-practices-apps)

**Key Quote from AWS:**
> "Generally, we recommend against using AWS CloudFormation parameters with the AWS CDK. [...] Use context values or environment variables instead."

For your use case, switch to context - it's the CDK-native way.