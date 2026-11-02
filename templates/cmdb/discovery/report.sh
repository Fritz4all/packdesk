#!/bin/sh
# PackDesk discovery for Linux: reports this computer and, with --neighbours, the devices it already knows on the
# network (from its own address table; it does not scan). Needs curl. Serial numbers need root.
# Run it by hand or from cron, e.g. once a day:
#   PACKDESK_KEY=<key> sh packdesk-discovery.sh [--neighbours]
set -eu
URL="{{ report_url }}"
: "${PACKDESK_KEY:?Set PACKDESK_KEY to the key of this discovery source}"

esc() { printf '%s' "$1" | tr -d '\000-\037' | sed 's/\\/\\\\/g; s/"/\\"/g'; }
dmi() { [ -r "/sys/class/dmi/id/$1" ] && cat "/sys/class/dmi/id/$1" 2>/dev/null || true; }

name=$(hostname)
serial=$(dmi product_serial)
os=""
[ -r /etc/os-release ] && os=$(. /etc/os-release && printf '%s' "${PRETTY_NAME:-}")
ip=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
items="{\"key\":\"$(esc "${serial:-$name}")\",\"name\":\"$(esc "$name")\",\"manufacturer\":\"$(esc "$(dmi sys_vendor)")\",\"model\":\"$(esc "$(dmi product_name)")\",\"serial_nr\":\"$(esc "$serial")\",\"properties\":{\"ip_address\":\"$(esc "$ip")\",\"operating_system\":\"$(esc "$os")\"}}"

if [ "${1:-}" = "--neighbours" ] && command -v ip >/dev/null; then
  neighbours=$(ip -4 neigh show 2>/dev/null | awk '$5 ~ /:/ && $NF != "FAILED" {print $1, $5}')
  old_ifs=$IFS; IFS='
'
  for line in $neighbours; do
    address=${line% *}; mac=${line#* }
    items="$items,{\"key\":\"$(esc "$mac")\",\"name\":\"$(esc "$address")\",\"properties\":{\"ip_address\":\"$(esc "$address")\",\"mac_address\":\"$(esc "$mac")\"}}"
  done
  IFS=$old_ifs
fi

curl --fail-with-body --silent --show-error -X POST "$URL" \
  -H "Authorization: Bearer $PACKDESK_KEY" -H "Content-Type: application/json" \
  --data-binary "{\"items\":[$items]}"
echo
