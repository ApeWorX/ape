# Documentation

## Overview

This repository has been updated to use the `apeworx/sphinx-ape` action for generating documentation. The workflow is configured to build and publish the documentation automatically when changes are pushed to the main branch or when a release is made.

## How to Use

1. **Run the Documentation Workflow**: The documentation is generated automatically when you push changes to the main branch or create a release. You can also run the workflow locally using `act -j docs`.

2. **Check Generated Documentation**: After the workflow runs, check the `docs/_build` directory for the generated HTML files. Open `index.html` in a web browser to view the documentation.

3. **Update Documentation**: To update the documentation, modify the markdown files in the `docs` directory and push the changes to the repository.

## Pre-commit Hooks

The pre-commit hooks have been updated to the latest versions to ensure code quality and consistency. You can run the pre-commit hooks locally using:

```bash
pre-commit run --all-files
```

## Additional Information

For more details on the changes made, refer to the PR description and the commit history. 