# Quick Start Guide

## First Time Setup

```bash
./setup.sh
```

This installs PyYAML and makes scripts executable.

## Prerequisites Check

```bash
./release.sh --check-deps
```

This will verify you have:
- Python 3.8+
- PyYAML
- git
- skopeo
- opm v1.47.0+

**Note**: On first run, required repositories will be automatically cloned to `staging/` directory.

## Basic Usage

### Dry Run (Recommended First)
```bash
./release.sh --dry-run
```

This will:
1. ✓ Fetch latest operator commit from GitHub API (no cloning!)
2. ✓ Get bundle image digest from quay.io
3. ✓ Preview what changes would be made
4. ✗ NOT modify any files
5. ✗ NOT commit changes

**In dry-run mode, NO files are modified.** You can safely run it multiple times.

### Actual Release
```bash
./release.sh
```

This will:
1. ✓ Fetch latest operator commit from GitHub API
2. ✓ Get bundle image digest from quay.io
3. ✓ Update FBC catalog template (`catalog-template.yaml`)
4. ✓ Regenerate catalog JSON (`catalog.json`)
5. ✓ Commit changes to git

After successful completion:
```bash
cd staging/instaslice-fbc
git push
```

## Common Scenarios

### Release Already Up-to-Date
If the latest operator commit is already in the catalog:
```
2025-10-02 08:56:53 - INFO - Catalog template already has the latest image
```
This is normal - the script will still regenerate the catalog to ensure consistency.

### Custom Paths
```bash
./release.sh \
  --operator-repo /custom/path/to/operator \
  --fbc-repo /custom/path/to/fbc
```

### Different OCP Version
```bash
./release.sh --ocp-version v4.18
```

### Verbose Logging
```bash
./release.sh --verbose
```

## Testing

### Run Unit Tests
```bash
make test-unit
```

### Run E2E Tests (requires real repos)
```bash
make test-e2e
```

### Run All Tests
```bash
make test
```

## Troubleshooting

### "FBC repository has uncommitted changes"
**Solution**: Commit or stash your changes first
```bash
cd ../instaslice-fbc
git status
git stash  # or commit your changes
```

### "Failed to inspect image: manifest unknown"
**Solution**: The bundle image doesn't exist yet for this commit. Wait for Konflux to build it, or check the commit SHA is correct.

### "Missing required dependencies"
**Solution**: Install the missing tools as shown in the error message.

## Output Explained

```
2025-10-02 08:56:48 - INFO - Latest commit on next: 336d5e6...
```
→ The latest commit from the operator's `next` branch

```
2025-10-02 08:56:53 - INFO - Image digest: sha256:107383b8...
```
→ The immutable SHA256 digest of the bundle container image

```
2025-10-02 08:56:54 - INFO - Regenerating catalog for v4.19...
```
→ Running `opm` to generate the FBC catalog JSON

```
2025-10-02 08:56:54 - INFO - DRY RUN - Changes not committed
```
→ In dry-run mode, no git commits are made

## What Gets Changed

The script modifies 2 files in the FBC repository:

1. `v4.19/catalog-template.yaml` - Updated with new bundle image reference
2. `v4.19/catalog/instaslice-operator/catalog.json` - Regenerated from template

Both are committed together with a descriptive message.

## Next Steps After Release

1. **Push to remote**:
   ```bash
   cd ../instaslice-fbc
   git push
   ```

2. **Monitor Konflux build**:
   - Visit: https://console.redhat.com/preview/application-pipeline/workspaces
   - Look for FBC catalog build for v4.19

3. **Verify ReleasePlan**:
   - The GitOps ReleasePlan automatically publishes to `registry.redhat.io`
   - Check: `konflux-release-data/tenants-config/.../instaslice-fbc-419-prod-release-plan.yaml`

4. **Confirm in OperatorHub**:
   - Once released, the operator appears in OpenShift's OperatorHub
   - Check your OpenShift cluster's OperatorHub for the update
