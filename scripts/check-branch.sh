#!/usr/bin/env bash
#
# check-branch.sh — local branch-policy guard for our FastAPI + Postgres project
#
# Runs on pre-commit and pre-push (via pre-commit framework).
#
# Hard blocks (stop the action):
#   1. Direct commits/pushes to protected branches (main/dev)
#   2. Invalid branch names (must follow naming convention)
#
# Warnings only (action continues):
#   3. Branch not cut from 'dev'
#
set -e

branch=$(git rev-parse --abbrev-ref HEAD)
protected="main master dev develop"

# ---------------------------------------------------------------------------
# 1. Block direct commits/pushes to protected branches
# ---------------------------------------------------------------------------
for p in $protected; do
  if [ "$branch" = "$p" ]; then
    echo "❌ Direct commits/pushes to '$branch' are blocked."
    echo "   Cut a feature branch from an updated dev:"
    echo "     git checkout dev && git pull origin dev && git checkout -b feature/your-task"
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# 2. Enforce branch naming convention
# ---------------------------------------------------------------------------
pattern="^(feature|features|bugfix|hotfix|chore|docs|refactor)/[a-z0-9._-]+$"
if ! echo "$branch" | grep -qE "$pattern"; then
  echo "❌ Branch name '$branch' is invalid."
  echo "   Use one of: feature/*, bugfix/*, hotfix/*, chore/*, docs/*, refactor/*"
  echo "   Example: feature/add-user-login"
  exit 1
fi

# ---------------------------------------------------------------------------
# 3. WARN ONLY — branch should be cut from 'dev' (does not block)
#    hotfix/* is exempt, since hotfixes branch from main by design.
# ---------------------------------------------------------------------------
if [[ "$branch" != hotfix/* ]]; then
  if git show-ref --verify --quiet refs/heads/dev; then
    if ! git merge-base --is-ancestor dev HEAD; then
      echo "⚠️  Heads up: '$branch' does not appear to be cut from 'dev'."
      echo "    Best practice is to branch from an updated dev:"
      echo "      git checkout dev && git pull origin dev && git checkout -b $branch"
      echo "    (Continuing anyway...)"
    fi
  fi
fi

echo "✅ Branch '$branch' OK"
exit 0
