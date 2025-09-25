# Git Commands Reference Guide

## Table of Contents
1. [Semantic Versioning Guide](#semantic-versioning-guide)
2. [Basic File Operations](#basic-file-operations)
3. [Branch Management](#branch-management)
4. [Remote Operations](#remote-operations)
5. [Merging and Conflict Resolution](#merging-and-conflict-resolution)
6. [Advanced Commands](#advanced-commands)

---

## Semantic Versioning Guide

This guide uses semantic versioning in commit messages to track changes:

### Version Format: `vMAJOR.MINOR.PATCH`

- **v0.0.1** - **Patch/Small Changes**: Bug fixes, typos, minor tweaks, code cleanup
  - Examples: `v0.0.1: Fix typo in README`, `v0.0.2: Update error message`

- **v0.1.0** - **Minor/Big Changes**: New features, significant updates, refactoring
  - Examples: `v0.1.0: Add user authentication`, `v0.2.0: Implement search functionality`

- **v1.0.0** - **Major/Production Ready**: Stable releases, breaking changes, major milestones
  - Examples: `v1.0.0: Initial production release`, `v2.0.0: Complete API redesign`

### Versioning Examples by Change Type

| Change Type | Version | Example Message |
|-------------|---------|-----------------|
| Typo fix | v0.0.1 | `v0.0.1: Fix spelling error in comments` |
| Bug fix | v0.0.2 | `v0.0.2: Resolve login validation issue` |
| Code cleanup | v0.0.3 | `v0.0.3: Remove unused imports` |
| New feature | v0.1.0 | `v0.1.0: Add password reset functionality` |
| Major refactor | v0.2.0 | `v0.2.0: Restructure database schema` |
| API changes | v0.3.0 | `v0.3.0: Update API endpoints for v2` |
| Production release | v1.0.0 | `v1.0.0: Launch stable version` |
| Breaking changes | v2.0.0 | `v2.0.0: Migrate to new framework` |

---

## Basic File Operations

### Adding Files to Staging Area
```bash
# Add specific file
git add filename.txt

# Add all files in current directory
git add .

# Add all modified files (excluding new files)
git add -u

# Add files interactively
git add -i
```

### Committing Changes
```bash
# Small changes (patches, minor fixes, typos)
git commit -m "v0.0.1: Fix typo in documentation"
git commit -m "v0.0.2: Update variable name for clarity"

# Big changes (new features, refactoring, significant updates)
git commit -m "v0.1.0: Add user authentication system"
git commit -m "v0.2.0: Implement payment gateway integration"

# Production ready (stable releases, major milestones)
git commit -m "v1.0.0: Initial production release"
git commit -m "v2.0.0: Major API redesign and performance improvements"

# Commit all tracked files (skip staging)
git commit -am "v0.0.3: Update error handling in login module"

# Commit with detailed message
git commit -m "v0.1.0: Add user dashboard" -m "- Implement user profile management
- Add activity tracking
- Include settings panel with theme options"
```

### Amending Commits
```bash
# Amend the last commit (add changes and/or modify message)
git commit --amend -m "v0.0.2: Fix typo in user validation (amended)"

# Amend without changing the message
git commit --amend --no-edit

# Amend and change author
git commit --amend --author="Name <email@example.com>"

# Example: Amend to fix version number
git commit --amend -m "v0.1.0: Add user authentication system"
```

---

## Branch Management

### Creating Branches
```bash
# Create a new branch
git branch branch-name

# Create and switch to new branch
git switch -c branch-name

# Create branch from specific commit
git branch branch-name commit-hash

# Create branch from specific remote branch
git switch -c branch-name origin/branch-name
```

### Switching Between Branches
```bash
# Switch to existing branch
git switch branch-name

# Switch to previous branch
git switch -

# Switch to main/master branch
git switch main

# Switch and create if branch doesn't exist
git switch -c branch-name
```

### Listing Branches
```bash
# List local branches
git branch

# List all branches (local and remote)
git branch -a

# List remote branches
git branch -r

# List branches with last commit info
git branch -v
```

### Deleting Branches
```bash
# Delete merged branch
git branch -d branch-name

# Force delete branch (even if unmerged)
git branch -D branch-name

# Delete remote branch
git push origin --delete branch-name
```

---

## Remote Operations

### Pushing Changes
```bash
# Push current branch to origin
git push

# Push specific branch to origin
git push origin branch-name

# Push and set upstream for new branch
git push -u origin branch-name

# Force push (use with caution)
git push --force
```

### Pulling Changes
```bash
# Pull from current branch's upstream
git pull

# Pull from specific remote and branch
git pull origin branch-name

# Pull with rebase instead of merge
git pull --rebase

# Pull all branches
git fetch --all
```

### Fetching Changes
```bash
# Fetch from origin without merging
git fetch

# Fetch from specific remote
git fetch origin

# Fetch and prune deleted remote branches
git fetch --prune
```

---

## Merging and Conflict Resolution

### Merging Branches
```bash
# Merge branch into current branch
git merge branch-name

# Merge with no fast-forward (creates merge commit)
git merge --no-ff branch-name

# Merge with squash (combine all commits into one)
git merge --squash branch-name

# Abort merge if conflicts arise
git merge --abort
```

### Handling Merge Conflicts

#### Identifying Conflicts
```bash
# Check status during conflict
git status

# See conflicted files
git diff --name-only --diff-filter=U
```

#### Resolving Conflicts
When conflicts occur, Git marks them in files like this:
```
<<<<<<< HEAD
Your changes
=======
Incoming changes
>>>>>>> branch-name
```

**Steps to resolve:**
1. Edit the conflicted files manually
2. Remove conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
3. Choose which changes to keep
4. Add resolved files: `git add filename`
5. Complete the merge: `git commit`

#### Useful Conflict Resolution Commands
```bash
# Use merge tool
git mergetool

# Accept all changes from current branch (ours)
git checkout --ours filename

# Accept all changes from merging branch (theirs)
git checkout --theirs filename

# Show conflict in different format
git diff --cc
```

### Rebasing (Alternative to Merging)
```bash
# Rebase current branch onto another
git rebase branch-name

# Interactive rebase for last n commits
git rebase -i HEAD~n

# Continue rebase after resolving conflicts
git rebase --continue

# Abort rebase
git rebase --abort
```

---

## Advanced Commands

### Viewing History
```bash
# View commit history
git log

# View concise history
git log --oneline

# View graphical history
git log --graph --oneline --all

# View changes in commits
git log -p
```

### Undoing Changes
```bash
# Unstage file
git reset filename

# Undo last commit (keep changes)
git reset --soft HEAD~1

# Undo last commit (discard changes)
git reset --hard HEAD~1

# Revert specific commit
git revert commit-hash
```

### Stashing Changes
```bash
# Stash current changes
git stash

# Stash with message
git stash push -m "Work in progress"

# List stashes
git stash list

# Apply latest stash
git stash pop

# Apply specific stash
git stash apply stash@{0}
```

### Checking Differences
```bash
# See unstaged changes
git diff

# See staged changes
git diff --staged

# Compare branches
git diff branch1..branch2

# Compare specific files
git diff filename
```

---

## Common Workflows

### Feature Branch Workflow
1. Create feature branch: `git switch -c feature-name`
2. Make changes and commit: `git add .` → `git commit -m "v0.1.0: Add new feature"`
3. Push branch: `git push -u origin feature-name`
4. Create pull/merge request (on GitHub/GitLab)
5. After review, merge and delete branch

### Hotfix Workflow
1. Create hotfix from main: `git switch -c hotfix-name` (while on main)
2. Make fix and commit: `git commit -am "v0.0.1: Fix critical security vulnerability"`
3. Push and create PR: `git push -u origin hotfix-name`
4. Merge into main and develop branches

### Sync Fork Workflow
1. Add upstream remote: `git remote add upstream original-repo-url`
2. Fetch upstream: `git fetch upstream`
3. Switch to main: `git switch main`
4. Merge upstream changes: `git merge upstream/main`
5. Push to your fork: `git push origin main`

---

## Quick Reference Cheat Sheet

| Command | Description |
|---------|-------------|
| `git status` | Show working directory status |
| `git log --oneline` | Show commit history |
| `git branch -a` | List all branches |
| `git switch -c name` | Create and switch to branch |
| `git add .` | Stage all changes |
| `git commit -m "v0.0.1: msg"` | Commit with versioned message |
| `git push -u origin branch` | Push new branch |
| `git pull` | Pull latest changes |
| `git merge branch` | Merge branch into current |
| `git stash` | Temporarily save changes |

---

## Best Practices

- **Commit often** with descriptive messages
- **Use branches** for features and experiments
- **Pull before push** to avoid conflicts
- **Review changes** before committing with `git diff`
- **Use meaningful branch names** (feature/user-auth, bugfix/login-error)
- **Keep commits atomic** (one logical change per commit)
- **Write clear commit messages** following conventional format
- **Regularly sync** with main branch to avoid large conflicts
