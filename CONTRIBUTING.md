# Contributing to PredixLab Campaign

Thank you for contributing. Start with [README](README.md) for the project's
scope, configuration, and operating limitations.

## Before making a change

- Use [GitHub Issues](https://github.com/predixlab/predixlab-campaign/issues) for reproducible bugs and focused proposals.
  Discuss substantial interface, schema, or workflow changes before implementing them.
- Report vulnerabilities privately using [SECURITY.md](SECURITY.md), not a public issue.
- Fork the repository and work on a focused branch. Keep unrelated fixes separate.

## Development setup

Requirements: Python 3.12+ and uv.

From the repository root:

```bash
uv sync --frozen --extra test
```

Follow README for optional services and local configuration. Use tracked examples
only as templates; keep real credentials and environment files outside Git.

## Validation

Run the smallest relevant checks while developing, then run the applicable project checks:

```bash
uv run python -m pytest
```

Mock queues, MongoDB, and ACS. Test consent, unsubscribe behavior, idempotency, delivery leases, and malformed messages. Use the console backend for local rendering; never send test mail to real customers.

## Pull requests

CI retains Python 3.12 for Azure Functions compatibility and uses uv 0.13.1 for
frozen test dependencies. Main-branch and manual runs can deploy after tests
pass; pull requests run tests without deploying. Do not treat CI tool upgrades
as approval to change the Functions runtime or application requirements.

- Describe the problem, intended behavior, and relevant issue.
- Follow existing project conventions; avoid unrelated refactors and dependency changes.
- Add focused regression tests for behavior changes and update public documentation in English.
- Include the commands run and their results; state any validation that could not run.
- Explain compatibility, data migration, configuration, and deployment consequences.
- Include screenshots for visible UI changes, with no customer or personal information.
- Do not include secrets, private endpoints, customer records, personal paths, or session
  profiles in source, fixtures, screenshots, logs, or generated artifacts. Review commit
  metadata and use a privacy-preserving identity if needed.

Be respectful and constructive. Harassment and disclosure of another person's
private information are not acceptable.

## Licensing

Contributions are submitted under the project's [Apache License 2.0](LICENSE).
Preserve copyright notices, third-party licenses, and source attribution. Do not
submit code, datasets, assets, or model files you do not have permission to share.
