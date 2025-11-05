# To run the script do:
# cd scripts
# chmod +x cloneRepos.sh
# ./cloneRepos.sh

#!/usr/bin/env bash
set -e

cd ..
mkdir -p projects
cd projects

# Avoid pulling large Git LFS files on clone (keeps it light)
export GIT_LFS_SKIP_SMUDGE=1

REPOS=(
  "https://github.com/n8n-io/n8n"
  "https://github.com/ant-design/ant-design"
  "https://github.com/redwoodjs/sdk"
  "https://github.com/microsoft/vscode"
  "https://github.com/nestjs/nest"
  "https://github.com/toeverything/AFFiNE"
  "https://github.com/daytonaio/daytona"
  "https://github.com/slidevjs/slidev"
  "https://github.com/chartdb/chartdb"
  "https://github.com/nrwl/nx"
  "https://github.com/panva/jose"
  "https://github.com/oclif/oclif"
  "https://github.com/egoist/tsup"
  "https://github.com/vitest-dev/vitest"
  "https://github.com/drizzle-team/drizzle-orm"
  "https://github.com/pnpm/pnpm"
  "https://github.com/prisma/prisma"
  "https://github.com/resend/react-email"
  "https://github.com/typescript-eslint/typescript-eslint"
)

# a shallow clone of each repo
for url in "${REPOS[@]}"; do
  echo "Cloning $url"
  git clone --depth=1 --filter=blob:none "$url"
done

echo "Done. Repos are in: $(pwd)"
