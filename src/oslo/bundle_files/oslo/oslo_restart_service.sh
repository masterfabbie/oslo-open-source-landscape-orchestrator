#!/bin/sh
# Restarts the instance agent (sapstartsrv) of one instance. Runs as root.
#
#   oslo_restart_service.sh normal <SID> <NR>
#       sapcontrol RestartService: sapstartsrv restarts itself; the instance keeps running.
#   oslo_restart_service.sh force <SID> <NR>
#       For a sapstartsrv that no longer answers: ends its process (TERM, then KILL) and
#       starts it again with sapcontrol StartService.
#
# Assumptions (not yet tested on a real host): sapcontrol of the host agent reaches the
# local sapstartsrv as root through its UNIX socket; the process is found by its profile
# argument "pf=/usr/sap/<SID>/SYS/profile/<SID>_<name><NR>_<host>".
set -u
PATH=/usr/bin:/bin:/usr/sbin:/sbin
SAPCONTROL=/usr/sap/hostctrl/exe/sapcontrol

fail() {
    echo "[ERROR]: $*"
    exit 1
}

[ $# -eq 3 ] || fail "usage: $0 normal|force <SID> <NR>"
MODE=$1
SID=$2
NR=$3
echo "$SID" | grep -Eq '^[A-Z][A-Z0-9]{2}$' || fail "invalid SID: $SID"
echo "$NR" | grep -Eq '^[0-9]{2}$' || fail "invalid instance number: $NR"
[ -x "$SAPCONTROL" ] || fail "$SAPCONTROL not found"

wait_started() {
    # Up to 5 minutes until the instance agent answers again.
    if "$SAPCONTROL" -nr "$NR" -function WaitforServiceStarted 300 0 >/dev/null 2>&1; then
        echo "Instance agent of $SID/$NR is running again"
    else
        fail "the instance agent of $SID/$NR did not answer within 5 minutes"
    fi
}

pids() {
    pgrep -f "sapstartsrv pf=/usr/sap/$SID/SYS/profile/${SID}_[A-Z]*${NR}_" || true
}

case "$MODE" in
normal)
    echo "Restarting the instance agent of $SID/$NR"
    "$SAPCONTROL" -nr "$NR" -function RestartService || fail "RestartService failed"
    sleep 2
    wait_started
    ;;
force)
    running=$(pids)
    if [ -n "$running" ]; then
        echo "Ending the instance agent of $SID/$NR (process $(echo $running))"
        kill $running 2>/dev/null || true
        n=0
        while [ -n "$(pids)" ] && [ $n -lt 10 ]; do
            sleep 1
            n=$((n + 1))
        done
        running=$(pids)
        if [ -n "$running" ]; then
            echo "Still running after 10 seconds, killing process $(echo $running)"
            kill -9 $running 2>/dev/null || true
            sleep 1
        fi
    else
        echo "No instance agent of $SID/$NR is running"
    fi
    echo "Starting the instance agent of $SID/$NR"
    "$SAPCONTROL" -nr "$NR" -function StartService "$SID" || fail "StartService failed"
    wait_started
    ;;
*)
    fail "unknown mode: $MODE"
    ;;
esac
