# Issue tracker: GitHub

Issues and specs for this repository live as GitHub issues. Use the `gh` CLI
for all operations. The configured `origin` remote identifies the repository.

## Conventions

- Create: `gh issue create --title "..." --body "..."`.
- Read: `gh issue view <number> --comments`.
- List: `gh issue list --state open`.
- Comment: `gh issue comment <number> --body "..."`.
- Label: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`.
- Close: `gh issue close <number> --comment "..."`.

## Pull requests as a triage surface

**PRs as a request surface: no.**

## Skill routing

When a skill says to publish to the issue tracker, create a GitHub issue.
When it says to fetch a ticket, run `gh issue view <number> --comments`.
