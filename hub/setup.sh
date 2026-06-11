#!/usr/bin/env bash
# Clones the external hub modules (Flowsint, MiroFish) into hub/vendor/.
# Vendored repos are gitignored — they stay their own upstream projects.
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p vendor

clone_or_update() {
  local repo="$1" dir="$2"
  if [ -d "vendor/$dir/.git" ]; then
    echo "==> Updating $dir"
    git -C "vendor/$dir" pull --ff-only || echo "    (pull failed, keeping current checkout)"
  else
    echo "==> Cloning $repo"
    git clone --depth 1 "$repo" "vendor/$dir"
  fi
}

clone_or_update https://github.com/reconurge/flowsint.git flowsint
clone_or_update https://github.com/666ghj/MiroFish.git mirofish

# MiroFish's frontend defaults to host port 3000, which collides with the
# SupoClip frontend. Remap it to 3100 (matches hub/modules.json).
for compose in vendor/mirofish/docker-compose.yml vendor/mirofish/docker-compose.yaml; do
  if [ -f "$compose" ] && grep -qE '"?3000:3000"?' "$compose"; then
    sed -i.bak -E 's/("?)3000:3000("?)/\13100:3000\2/' "$compose"
    echo "==> Remapped MiroFish frontend host port 3000 -> 3100 in $compose"
  fi
done

cat <<'EOF'

Setup complete. Next steps:

  1. Configure each module's .env:
       - SupoClip:  ../.env            (ASSEMBLY_AI_API_KEY, LLM, provider key)
       - Flowsint:  vendor/flowsint    (AUTH_SECRET, MASTER_VAULT_KEY_V1, NEO4J_PASSWORD)
       - MiroFish:  vendor/mirofish    (LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME, ZEP_API_KEY)

  2. Start everything:   make up
  3. Open the hub:       http://localhost:8090

Note: SupoClip publishes Redis on 6379. If Flowsint's stack also publishes
Redis/Postgres on the host and you hit a port conflict, remap the ports in
vendor/flowsint's compose file.
EOF
