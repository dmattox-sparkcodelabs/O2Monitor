#!/bin/bash
#
# Setup git hooks for O2Monitor development
#
# Run this after cloning the repo to install the pre-commit hook
# that prevents accidental commit of secrets.
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

echo "Setting up git hooks for O2Monitor..."

# Create hooks directory if it doesn't exist
mkdir -p "$HOOKS_DIR"

# Create pre-commit hook
cat > "$HOOKS_DIR/pre-commit" << 'HOOK'
#!/bin/bash
#
# Pre-commit hook to prevent accidental commit of secrets
#

SECRET_PATTERNS=(
    'github_pat_[A-Za-z0-9_]+'
    'routing_key:\s*[a-f0-9]{32}'
    'api_token:\s*[A-Za-z0-9_-]{20,}'
    'hc-ping\.com/[a-f0-9-]{36}'
    'sk-[A-Za-z0-9]{48}'
    'password\s*[:=]\s*["\047][^"\047]{8,}["\047]'
    'secret\s*[:=]\s*["\047][^"\047]{8,}["\047]'
)

RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACMR)

if [ -z "$STAGED_FILES" ]; then
    exit 0
fi

FOUND_SECRETS=0

for pattern in "${SECRET_PATTERNS[@]}"; do
    MATCHES=$(git diff --cached --diff-filter=ACMR -U0 | grep -iE "^\+" | grep -iE "$pattern" || true)

    if [ -n "$MATCHES" ]; then
        if [ $FOUND_SECRETS -eq 0 ]; then
            echo -e "${RED}========================================${NC}"
            echo -e "${RED}  COMMIT BLOCKED: Potential secrets found${NC}"
            echo -e "${RED}========================================${NC}"
            echo ""
        fi
        FOUND_SECRETS=1
        echo -e "${YELLOW}Pattern:${NC} $pattern"
        echo -e "${YELLOW}Found:${NC}"
        echo "$MATCHES" | head -5
        echo ""
    fi
done

if [ $FOUND_SECRETS -ne 0 ]; then
    echo -e "${RED}Put credentials in .secrets.md (gitignored), not in code.${NC}"
    echo "To bypass: git commit --no-verify"
    exit 1
fi

exit 0
HOOK

chmod +x "$HOOKS_DIR/pre-commit"

echo "Pre-commit hook installed successfully."
echo ""
echo "The hook will block commits containing patterns like:"
echo "  - GitHub PATs (github_pat_...)"
echo "  - API keys and routing keys"
echo "  - Passwords in config files"
echo ""
echo "Don't forget to create .secrets.md with your credentials!"
