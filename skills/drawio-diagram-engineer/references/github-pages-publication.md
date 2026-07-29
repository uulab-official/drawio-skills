# GitHub Pages publication

Read this reference when a repository should publish its architecture review site and retain evidence for each source revision.

## Install the workflow

Copy [github-pages-workflow.yml](../assets/github-pages-workflow.yml) to `.github/workflows/diagram-review-pages.yml`. Change `DIAGRAM_SOURCE` and `ARCHITECTURE_POLICY` to repository paths containing the source model and policy pack.

The recipe:

- builds and strictly validates a fresh bundle;
- publishes the portable review site and enforces policy;
- uploads `reports/findings.sarif` to GitHub code scanning;
- retains `diagram-review-<commit-sha>` as a non-overwritten workflow artifact;
- deploys the same static directory to GitHub Pages.

Every third-party action is pinned to a full commit SHA. Review and deliberately update those pins instead of replacing them with floating tags.

## Repository setup

In the repository Pages settings, choose **GitHub Actions** as the source. The workflow already requests the minimum contents, Pages, identity-token, and code-scanning permissions needed by its steps.

Fork pull requests do not receive write permissions. Keep publication on protected branches or explicit `workflow_dispatch` runs, and run read-only build/policy checks in pull requests if contributor feedback is needed.

## Immutable evidence

The Pages URL points to the latest successful deployment. The workflow artifact name includes the full source commit SHA and sets `overwrite: false`, so reviewers can recover the exact site used for a prior decision. Keep `review.json`, `reports/policy.json`, and `reports/findings.sarif` together with the HTML and SVG pages.
