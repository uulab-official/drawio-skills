# GitHub Pages publication

Read this reference when a repository should publish its architecture review site and retain evidence for each source revision.

## Install the workflow

Copy [github-pages-workflow.yml](../assets/github-pages-workflow.yml) to `.github/workflows/diagram-review-pages.yml`. Change `DIAGRAM_SOURCE`, the policy and policy-test paths, `REVIEW_OWNERSHIP`, and `CODEOWNERS_FILE` to repository-owned files. Remove optional layers that the repository does not use.

The recipe:

- builds and strictly validates a fresh bundle;
- runs deterministic policy cases with complete rule/exception assertion coverage;
- publishes the portable review site and enforces composed policy plus ownership coverage;
- embeds the immutable commit, repository, source link, bundle/artifact hashes, and hosted base URL;
- appends `reports/summary.md` to the GitHub job summary;
- creates a GitHub Check from the generated request and signs the review manifest with a custom GitHub/Sigstore attestation;
- uploads `reports/findings.sarif` to GitHub code scanning;
- retains `diagram-review-<commit-sha>` as a non-overwritten workflow artifact;
- deploys the same static directory to GitHub Pages.

Every third-party action is pinned to a full commit SHA. Review and deliberately update those pins instead of replacing them with floating tags.

## Repository setup

In the repository Pages settings, choose **GitHub Actions** as the source. The workflow requests contents read plus Pages, identity-token, attestations, Checks, and code-scanning writes. Remove `checks: write` or `attestations: write` together with the corresponding optional step when those adapters are not used.

Fork pull requests do not receive write permissions. Keep Pages deployment on protected branches or explicit `workflow_dispatch` runs. A pull-request workflow may run the same build/publish command with read-only permissions and append `reports/summary.md`; skip code-scanning upload and deployment for untrusted forks. If the pull request has a separate preview host, pass its immutable URL through `--public-base-url` so changed-page links point to that candidate rather than the latest main deployment.

## Immutable evidence

The Pages URL points to the latest successful deployment. The workflow artifact name includes the full source commit SHA and sets `overwrite: false`, so reviewers can recover the exact site used for a prior decision. `review.json` binds that site to the commit and bundle digests; the custom attestation signs that subject through GitHub's OIDC-backed attestation service. Keep it together with policy, ownership, summary, SARIF, Checks, and attestation reports.
