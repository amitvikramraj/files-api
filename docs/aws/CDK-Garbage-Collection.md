# CDK Garbage Collection

> AI Overview

ref:
- https://aws.amazon.com/blogs/devops/announcing-cdk-garbage-collection/
- https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-gc.html

CDK garbage collection (“GC”) is a **CDK CLI feature that helps you clean up old, unused CDK assets** that accumulate in the **bootstrap** resources (the S3 bucket and/or ECR repo created by `cdk bootstrap`). It’s meant to reduce storage bloat and cost without you having to guess which asset objects/images are safe to delete. ([Amazon Web Services, Inc.][1])

## What “CDK assets” are (and why they pile up)

When your stacks use `fromAsset()` (zip/file assets to **S3**) or `fromAssetImage()` (docker image assets to **ECR**), CDK uploads a new “asset” whenever content changes (hash changes). Over time, your bootstrap S3 bucket/ECR repo can fill with **older hashes** that are no longer referenced by any deployed stack template.

## What `cdk gc` actually does

At a high level:

1. **Scans the bootstrap bucket/repo** in an environment (account/region).
2. **Determines which assets are still referenced** by looking at existing CloudFormation templates in that same environment.

   * For S3 assets, CDK checks whether assets are referenced by CloudFormation templates; if not referenced, they’re treated as unused/isolated.
3. Then, depending on your settings, it will **print, tag, and/or delete** unused assets.

It runs **per environment** (account + region), and you can pass one or more environments like `aws://123456789012/us-east-1`.

## Why you must pass `--unstable=gc`

GC is considered “in development/preview” from an interface standpoint, so you must opt in:

```bash
cdk gc --unstable=gc
```

AWS describes the current features as production-ready/safe, but warns the command’s scope/API may change—hence the explicit opt-in.

## The knobs you’ll actually use

### 1. `--type`: what to clean

* `--type=s3` → only the bootstrap S3 bucket
* `--type=ecr` → only the bootstrap ECR repo
* default `all`

### 2. `--action`: how aggressive to be

* `print` → show what would be unused; **no changes**
* `tag` → tag newly identified unused assets; **no deletion**
* `delete-tagged` → delete assets already tagged (in your configured buffer window); **doesn’t tag new ones**
* `full` (default) → “do everything” (tag new + delete eligible tagged)

### 3 Safety buffers (the most important part)

There are *two different* safety ideas:

**A. `--created-buffer-days` (default 1)**
“Don’t touch anything created too recently.” This reduces risk if a deployment is in-flight or you just uploaded assets.

**B. `--rollback-buffer-days` (default 0)**
This controls “two-step delete” behavior:

* If you set it to N > 0, GC will **tag** unused assets first (instead of deleting), and only **delete after they’ve stayed tagged long enough**. This is especially useful if you deploy via pipelines/templates and want to ensure rollback windows.

### 4. `--confirm`

By default, it will prompt you before deleting. You can set `--confirm false` for automation (use with care).

## A simple mental model: “isolated → (maybe tag) → (maybe delete)”

* “Isolated/unused” means: **not referenced by currently present stack templates** in that environment.
* If you configured rollback buffering, GC tags first and deletes in a later run after the buffer window. ([Amazon Web Services, Inc.][1])

## Practical commands (good defaults)

### 1. Safest first step: dry-run style inventory

```bash
cdk gc --unstable=gc --action=print
```

This helps you see how much would be considered unused before you delete anything.

### 2. Conservative cleanup for real environments (tag now, delete later)

Example: tag unused now, then let them sit for 30 days before deletion:

```bash
cdk gc --unstable=gc --action=full --rollback-buffer-days=30 --created-buffer-days=10
```

This matches the doc’s idea of deleting only things that are both older and have remained isolated long enough.

### 3. Cleanup only things you already tagged (nice for scheduled runs)

```bash
cdk gc --unstable=gc --action=delete-tagged --rollback-buffer-days=30
```

This deletes previously-tagged assets older than your buffer.

### 4. “Nuke unused right now” (mostly for dev/test)

The blog shows setting both buffers to 0 to delete immediately (useful for demo/dev, riskier for prod):

```bash
cdk gc --unstable=gc --rollback-buffer-days=0 --created-buffer-days=0
```


## Important limitation / gotcha (race condition)

AWS calls out an edge case: if GC runs **between asset upload and stack deployment**, it might see the new asset in the bucket/repo but not yet see a template referencing it, and could delete it. They recommend not deploying while running GC, and/or using `--created-buffer-days` to avoid recently-created assets. If it happens, redeploying re-uploads the asset. ([Amazon Web Services, Inc.][1])

---

If you tell me how you deploy (local `cdk deploy` vs CI/CD pipeline that deploys synthesized templates) and whether this is dev or prod, I can suggest a “sane default” GC schedule + exact flags (usually “print → tag → delete-tagged” with buffers).

