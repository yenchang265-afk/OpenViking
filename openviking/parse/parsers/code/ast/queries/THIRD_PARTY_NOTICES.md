Third-Party Notices for Code Skeleton Queries
=============================================

This directory contains Business Data Platform-maintained tree-sitter tag queries used for
code skeleton extraction. The query set has mixed provenance:

- Some `.scm` files were initially adapted from Aider's RepoMap query set.
- Some `.scm` files were authored or substantially rewritten by Business Data Platform.
- All files in this directory are maintained by Business Data Platform going forward.

Do not assume that every file in this directory is vendored from Aider.

Aider Source
------------

The Aider-derived query files were adapted from:

https://github.com/Aider-AI/aider/tree/main/aider/queries/tree-sitter-language-pack

Reference revision:

5dc9490bb35f9729ef2c95d00a19ccd30c26339c

Aider is licensed under the Apache License, Version 2.0. A copy of that license
is included in this directory as `AIDER_LICENSE.txt` because this query set
contains Aider-derived material.

Aider's query directory states that its `.scm` files are adapted from the
language repositories listed by tree-sitter-language-pack:

https://github.com/Goldziher/tree-sitter-language-pack/blob/main/sources/language_definitions.json

See the tree-sitter-language-pack project for information about those language
repositories:

https://github.com/Goldziher/tree-sitter-language-pack/

Business Data Platform Maintenance Policy
-----------------------------

Business Data Platform may modify, replace, or add tag query files in this directory to
improve code skeleton extraction quality. For future changes:

- Keep `AIDER_LICENSE.txt` while any Aider-derived query remains.
- Add a short file header or update this notice when adding a query with a
  third-party source.
- For Business Data Platform-authored queries, no third-party attribution is required unless
  they are based on another project.
- If a previously Aider-derived query is replaced with a fully original
  Business Data Platform implementation, record that change in the file or this notice.
