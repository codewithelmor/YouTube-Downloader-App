---
description: Compose a Conventional Commits message, then ask the user whether to continue and run the commit
argument-hint: [optional hint: scope, ticket number, or extra context]
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git add:*), Bash(git commit:*), AskUserQuestion
---

# Prepare a Commit Message

Your job is to **compose the commit message, show it, and then ask the user whether to continue** before anything is committed.

## Hard rules

- **NEVER run** `git commit` or `git add` until the user has explicitly confirmed in the confirmation step below. Without a clear "yes", do not run them.
- **NEVER run** `git push`, `git reset`, `git stash`, `git checkout`, or any other command that changes the repository, even after confirmation. Confirmation covers only the shown `git add` and `git commit` commands.
- Before confirmation, only use read-only git commands to understand the changes.
- Do not claim the changes were committed unless the commit command actually ran and succeeded.
- Do not add "Co-authored-by", "Generated with", or any AI attribution line unless the user asks for it.

## Context

- Branch and status (works on any branch name, detached HEAD, or a repo with no commits yet): !`git status --short --branch`
- Staged changes: !`git diff --cached --stat`
- Unstaged changes: !`git diff --stat`
- Recent commits (for style and scope reference; may be empty in a new repo): !`git log --oneline -10 --all`

User hint (optional): $ARGUMENTS

## Steps

1. **Check what will be committed.**
   - If there are staged changes, use `git diff --cached` to read them. Compose the message for the staged changes **only**.
   - If nothing is staged but there are unstaged or untracked files, do not guess. Tell the user nothing is staged, and prepare the `git add` command (with specific file paths, not `git add .`) followed by the commit command, both for the user to run.
   - If there are no changes at all, say so and stop.
   - If the repository has no commits yet (status shows "No commits yet"; the recent commits list is empty), this is the first commit. That is normal, not an error. Do not run `git log` without `--all`, since it fails on an empty repo. Compose the message from the staged files; for a fresh project, `chore: initial commit` (or `feat: ...` if it clearly delivers a feature) is fine.
   - Never assume a branch name such as `main` or `master`. Use whatever the status line shows, and do not add a branch name to the commit command.
2. **Read the actual diff** (`git diff --cached`, or `git diff` when preparing a `git add` suggestion) so the message is based on the real changes, not only on the file names.
3. **Check if the changes should be split.** If the diff mixes unrelated changes (for example a feature and an unrelated refactor), recommend separate commits. Prepare one `git add` and `git commit` pair for each commit.
4. **Compose the message** using the format and rules below.
5. **Show the result** using the output format below.
6. **Ask the user whether to continue** (see "Confirmation step"). This step is mandatory every time the command is called, even when the message looks perfect.

## Confirmation step

After showing the result, call the `AskUserQuestion` tool with one question, for example "Do you want to continue and commit with this message?", and these options:

- **Commit now**: run the shown `git add` (only if one was prepared) and `git commit` commands exactly as shown.
- **Edit the message**: the user gives changes; update the message, show it again, and ask again.
- **Cancel**: stop and run nothing.

Handling the answer:

- **Commit now**: run the commands as shown, in order, one after the other. If a command fails (for example a hook rejects the commit), show the error and do not retry with flags like `--no-verify`. If it succeeds, confirm with the short hash from `git log --oneline -1`.
- **Edit the message** (or free text from "Other"): apply the change, show the new command, and ask the confirmation question again.
- **Cancel**, or no clear answer: do not run anything. Say that nothing was committed.
- If you recommended splitting into several commits, ask once per commit, in order, and run each only after its own confirmation.
- If there was nothing to commit (no changes), skip this step.

## Message format (Conventional Commits 1.0.0)

```
<type>[optional scope][!]: <description>

[optional body]

[optional footer(s)]
```

### Types

| Type | Use it for |
|---|---|
| `feat` | New feature for the user or API consumer (MINOR) |
| `fix` | Bug fix (PATCH) |
| `docs` | Documentation only |
| `style` | Formatting only, no logic change |
| `refactor` | Code restructure, same behavior |
| `perf` | Performance improvement |
| `test` | Add or correct tests |
| `build` | Build system or dependencies |
| `ci` | CI/CD configuration or scripts |
| `chore` | Other maintenance that does not fit above |
| `revert` | Revert a previous commit |

Choose the type in this order: new behavior = `feat`; corrected behavior = `fix`; only docs = `docs`; only tests = `test`; formatting only = `style`; faster = `perf`; restructure without behavior change = `refactor`; dependencies or build = `build`; pipeline = `ci`; anything else = `chore`.

### Scope

- Optional. Short lowercase noun for the affected area, such as `auth`, `api`, `ui`, `db`, `deps`.
- Prefer a scope already used in the recent commits (if there are none, choose one from the changed paths or omit it).
- Omit it when the change touches many areas.

### Description (first line)

- Imperative mood: "add", "fix", "remove" (not "added" or "adds").
- Lowercase after the colon, **no period** at the end.
- Maximum **72 characters** for the whole first line.
- Be specific. Do not repeat the type in the description.

### Body (optional, but add it when the reason is not obvious)

- Explain **why** the change was made, not what the diff already shows.
- Leave one blank line after the first line. Wrap lines at about 72 characters.
- Skip the body for small, self-explanatory changes.

### Footers (only when relevant)

- Issue references: `Closes #123`, `Refs: #123`, or the work item key from the user hint or branch name (for example `Refs: PROJ-123`).
- Breaking change: add `!` before the colon **and** a `BREAKING CHANGE: <what breaks and how to migrate>` footer.

### Do not

- Do not write vague messages such as "update", "fix bug", or "changes".
- Do not mix unrelated changes in one message.
- Do not invent issue numbers, ticket keys, or reasons that are not in the diff, branch name, or user hint. If the reason for the change is unclear, keep the body short and ask the user at the end.

## Output format

Reply with these parts, in this order and nothing else:

1. **A one-line summary** of what you found (for example "3 staged files, 1 logical change").
2. **The command** in a single fenced `bash` code block, ready to copy and run.
3. **Notes** (only if needed): a warning, a suggestion to split the commit, or one question about missing context.

### How to write the command

- Use `git commit` with one `-m` flag for the first line, and one extra `-m` flag for each body paragraph and each footer. Do **not** use heredocs or `$(...)`, so the command works in Bash, PowerShell, and Windows terminals.
- Wrap each message in **double quotes**. Avoid backticks, `$`, `!`, and double quotes inside the message text, so it does not break in the shell. Reword if needed.
- Put the `git add` line first (with specific file paths) **only** when nothing is staged.
- Never add flags such as `--no-verify`, `--amend`, or `--no-gpg-sign`.

### Example output

Summary: 2 staged files, 1 logical change (new endpoint).

```bash
git commit -m "feat(auth): add refresh token endpoint" -m "Access tokens now expire after 15 minutes. Clients can request a new access token with the refresh token instead of logging in again." -m "Closes #142"
```

End the text with this line: "Review the message, then choose below whether to continue." Then ask the confirmation question.
