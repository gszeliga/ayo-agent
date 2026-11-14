#!/usr/bin/env bash
# Open psql on one of the app's databases.
# Usage: scripts/db_shell.sh [local|remote|migrations] [--write] [-- psql args...]
#   local       the dev DB from scripts/dev_db.sh (localhost:5433), the default
#   remote      DATABASE_URL (shell first, then .env)
#   migrations  MIGRATIONS_DATABASE_URL (the direct Neon endpoint)
#   --write     remote targets are read-only unless this is given (asks for the host);
#               read-only uses the direct endpoint (Neon's pooler rejects startup options)
# The URL is split into PG* variables, so the password never appears in ps or the terminal.
# .env is read from the project root (AYO_ENV_FILE overrides it) and never sourced.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${AYO_ENV_FILE:-${ROOT}/.env}"

die() { echo "db_shell: $*" >&2; exit 1; }
usage() { echo "usage: $0 [local|remote|migrations] [--write] [-- psql args...]" >&2; exit 2; }

target=local
write=false
psql_args=()
while [ $# -gt 0 ]; do
  case "$1" in
    local|remote|migrations) target="$1" ;;
    --write) write=true ;;
    --) shift; psql_args=("$@"); break ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
  shift
done

command -v psql >/dev/null || die "psql not found; install the PostgreSQL client"

# The value of NAME: the shell's variable if set and non-empty, else the last NAME= in .env.
read_setting() {
  local name="$1" value="${!1:-}"
  if [ -z "${value}" ] && [ -f "${ENV_FILE}" ]; then
    value="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${name}[[:space:]]*=" "${ENV_FILE}" \
      | tail -n 1 | sed -E "s/^[^=]*=[[:space:]]*//; s/[[:space:]]+$//")" || true
    case "${value}" in
      \"*\") value="${value#\"}"; value="${value%\"}" ;;
      \'*\') value="${value#\'}"; value="${value%\'}" ;;
    esac
  fi
  printf '%s' "${value}"
}

urldecode() { local s="${1//+/ }"; printf '%b' "${s//%/\\x}"; }

case "${target}" in
  local) url="postgresql://ayo:ayo@localhost:5433/ayo" ;;
  remote) url="$(read_setting DATABASE_URL)" ;;
  migrations) url="$(read_setting MIGRATIONS_DATABASE_URL)" ;;
esac
[ -n "${url}" ] || die "no URL for '${target}' (shell or ${ENV_FILE})"

# scheme://user:password@host:port/db?query (password, port and query optional)
re='^postgres(ql)?(\+[a-z0-9]+)?://([^:@/]+)(:([^@]*))?@([^:/?]+)(:([0-9]+))?/([^?]+)(\?(.*))?$'
[[ "${url}" =~ ${re} ]] || die "the URL for '${target}' is not postgresql://user[:password]@host[:port]/db"
PGUSER="$(urldecode "${BASH_REMATCH[3]}")"
PGPASSWORD="$(urldecode "${BASH_REMATCH[5]}")"
PGHOST="${BASH_REMATCH[6]}"
PGPORT="${BASH_REMATCH[8]:-5432}"
PGDATABASE="$(urldecode "${BASH_REMATCH[9]}")"
query="${BASH_REMATCH[11]}"
unset url
export PGUSER PGPASSWORD PGHOST PGPORT PGDATABASE

IFS='&' read -ra params <<<"${query}"
for param in "${params[@]}"; do
  case "${param}" in
    sslmode=*) export PGSSLMODE="${param#*=}" ;;
    channel_binding=*) export PGCHANNELBINDING="${param#*=}" ;;
  esac
done

case "${PGHOST}" in
  localhost|127.0.0.1|::1) remote=false ;;
  *) remote=true ;;
esac

mode=read-write
if ${remote} && ! ${write}; then
  mode=read-only
  # The server enforces it from the connection's startup options, so psql -X cannot skip it.
  # Neon's pooler (PgBouncer) rejects startup options, so read-only goes to the direct endpoint.
  PGHOST="${PGHOST/-pooler./.}"
  export PGOPTIONS="-c default_transaction_read_only=on"
elif ${remote}; then
  read -r -p "Read-write on ${PGHOST}. Type the host to confirm: " answer
  [ "${answer}" = "${PGHOST}" ] || die "host does not match; not connecting"
fi

echo "db_shell: ${target} -> ${PGHOST}:${PGPORT}/${PGDATABASE} (${mode})" >&2
exec psql "${psql_args[@]}"
