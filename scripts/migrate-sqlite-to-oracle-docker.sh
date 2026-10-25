#!/usr/bin/env bash
# Host wrapper for the verified database transfer; never starts an application.
set -Eeuo pipefail
umask 077

usage() {
  cat <<'USAGE'
Usage: migrate-sqlite-to-oracle-docker.sh [options]

Default: require a stopped source and validate without changing Oracle.
--apply stops the source, backs it up, validates, transfers, and checks Oracle.
The application is never started or restarted automatically.

  --apply                  Stop/back up and perform the verified transfer
  --dry-run                Validate only (default; source must be stopped)
  --container NAME         Existing source container (default: codex-lb)
  --image IMAGE            Updated image (default: codex-lb:oracle)
  --env-file PATH          Oracle/runtime settings (default: .env.oracle)
  --build                  Build the image from this repository before checks
  --data-dir PATH          Source container data directory (default: /var/lib/codex-lb)
  --source-sqlite PATH     Database inside that directory (default: DATA_DIR/store.db)
  --source-key-file PATH    Custom key path inside helper containers
  --backup-dir PATH        New host backup directory; existing paths are refused
  --network NAME           Docker network used by every helper
  --mount SPEC             Additional Docker mount; repeatable (e.g. wallet)
  -h, --help               Show this help

Example:
  bash scripts/migrate-sqlite-to-oracle-docker.sh --build --apply --env-file .env.oracle

Stop other workers/instances sharing the source or Oracle target first. Preserve
custom keys/wallets outside the data directory separately. Do not put database
URLs on this command line; the environment file is passed directly to Docker.
USAGE
}

die() { printf 'Migration error: %s\n' "$*" >&2; exit 1; }

require_value() {
  [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || die "Missing value for $1"
}

mode=dry-run
mode_selected=false
container=codex-lb
image=codex-lb:oracle
env_file=.env.oracle
data_dir=/var/lib/codex-lb
source_sqlite=
key_file=
backup_dir=
network=
build=false
mounts=()
while (( $# )); do
  case "$1" in
    --apply|--dry-run)
      requested_mode=${1#--}
      if [[ "$mode_selected" == true && "$mode" != "$requested_mode" ]]; then
        die '--apply and --dry-run cannot be combined'
      fi
      mode=$requested_mode; mode_selected=true; shift ;;
    --build) build=true; shift ;;
    --container) require_value "$@"; container=$2; shift 2 ;;
    --image) require_value "$@"; image=$2; shift 2 ;;
    --env-file) require_value "$@"; env_file=$2; shift 2 ;;
    --data-dir) require_value "$@"; data_dir=$2; shift 2 ;;
    --source-sqlite) require_value "$@"; source_sqlite=$2; shift 2 ;;
    --source-key-file) require_value "$@"; key_file=$2; shift 2 ;;
    --backup-dir) require_value "$@"; backup_dir=$2; shift 2 ;;
    --network) require_value "$@"; network=$2; shift 2 ;;
    --mount) require_value "$@"; mounts+=("$2"); shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1 (use --help)" ;;
  esac
done

[[ -f "$env_file" && -r "$env_file" ]] || die 'The environment file must exist and be readable'
[[ "$container" != -* && "$image" != -* ]] || die 'Container and image must not start with a dash'
[[ "$data_dir" == /* && "$data_dir" != / ]] || die '--data-dir must be an absolute container directory below /'
data_dir=${data_dir%/}
[[ -n "$source_sqlite" ]] || source_sqlite="$data_dir/store.db"
[[ "$source_sqlite" == "$data_dir/"* && "$source_sqlite" != */../* ]] || \
  die '--source-sqlite must be inside --data-dir so the backup includes it'
[[ -z "$key_file" || "$key_file" == /* ]] || die '--source-key-file must be an absolute container path'
if [[ -n "$backup_dir" && ( -e "$backup_dir" || -L "$backup_dir" ) ]]; then
  die 'The backup directory already exists; choose a new path'
fi
command -v docker >/dev/null || die 'Docker CLI is required'

stage='Docker/source inspection'
source_stop_attempted=false
backup_complete=false
on_exit() {
  local status=$?
  if (( status )); then
    printf 'Stopped at stage: %s. No application start or automatic transfer retry was attempted.\n' "$stage" >&2
    if [[ "$source_stop_attempted" == true ]]; then
      printf 'The source will not be restarted automatically. Inspect container/database state before recovery.\n' >&2
    fi
    if [[ -n "$backup_dir" && -d "$backup_dir" ]]; then
      printf 'Retained backup directory: %s (copy completed: %s)\n' "$backup_dir" "$backup_complete" >&2
    fi
  fi
}
trap on_exit EXIT

docker info >/dev/null
running() { docker container inspect --format '{{.State.Running}}' "$container"; }
state=$(running)
[[ "$state" == true || "$state" == false ]] || die 'Could not determine source running state'
if [[ "$mode" == dry-run && "$state" == true ]]; then
  die 'Dry run requires a stopped source; stop it first or select --apply'
fi

destinations=$(docker container inspect --format '{{range .Mounts}}{{println .Destination}}{{end}}' "$container")
data_mounted=false
while IFS= read -r destination; do
  [[ -n "$destination" ]] || continue
  destination=${destination%/}
  [[ -n "$destination" ]] || die 'Source has a root mount that hides the image'
  case "$destination/" in
    /app/|/app/app/|/app/app/*) die 'Source application-code mounts would hide the updated image' ;;
  esac
  if [[ "$data_dir/" == "$destination/"* ]]; then data_mounted=true; fi
done <<< "$destinations"
[[ "$data_mounted" == true ]] || die 'Source data directory is not covered by an inherited Docker mount'

common=(--volumes-from "$container" --env-file "$env_file")
[[ -z "$network" ]] || common+=(--network "$network")
for mount in "${mounts[@]}"; do common+=(--mount "$mount"); done
run_python() { docker run --rm "${common[@]}" --entrypoint python "$image" "$@"; }
db() { run_python -m app.db.migrate "$@"; }
transfer_args=(migrate-to-oracle --source-sqlite "$source_sqlite")
[[ -z "$key_file" ]] || transfer_args+=(--source-key-file "$key_file")

if [[ "$build" == true ]]; then
  stage='image build'
  repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
  docker build --tag "$image" --file "$repo_dir/Dockerfile" "$repo_dir"
fi
stage='image/driver/Oracle preflight'
docker image inspect "$image" >/dev/null
run_python -c 'import oracledb; import app.db.oracle_transfer'
db oracle-check

if [[ "$mode" == dry-run ]]; then
  stage='source/target dry run'
  db "${transfer_args[@]}" --dry-run
  printf 'Dry run complete. No source stop, backup, transfer or application start was performed.\n'
  exit 0
fi

stage='backup reservation'
if [[ -z "$backup_dir" ]]; then
  [[ -n "${HOME:-}" ]] || die 'Set --backup-dir when HOME is unavailable'
  backup_dir="$HOME/codex-lb-backups/$(date -u +%Y%m%dT%H%M%SZ)-$$"
fi
mkdir -p -- "$(dirname -- "$backup_dir")"
mkdir -m 700 -- "$backup_dir"
stage='source stop'
source_stop_attempted=true
docker stop "$container" >/dev/null
[[ "$(running)" == false ]] || die 'Source is still running after stop'

stage='complete data-directory backup'
docker cp "$container:$data_dir/." "$backup_dir/"
[[ "$(running)" == false ]] || die 'Source restarted during backup; stop external workers/orchestrators'
backup_complete=true

stage='source/target dry run'
db "${transfer_args[@]}" --dry-run
stage='verified transfer'
db "${transfer_args[@]}"
stage='Oracle schema check'
db check

printf '\nMigration and schema check complete. Source remains stopped. Backup: %s\n' "$backup_dir"
printf 'Keep the same key/archive volume; adapt original ports and deployment options before cutover.\n'
printf 'Example application command (not executed):\n'
printf '%q ' docker run -d --name "$container-oracle" "${common[@]}" \
  -p 2455:2455 -p 1455:1455 --restart unless-stopped "$image"
printf '\n'
