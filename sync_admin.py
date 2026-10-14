"""إدارة الفروع (على المركز):  python sync_admin.py add-node BR02 [وصف] | list | remove BR02"""
import sys
from erp_app import nodesync

def main(a):
    if not a:
        print(__doc__); return 1
    c = a[0]
    if c == "add-node" and len(a) >= 2:
        k = nodesync.add_node(a[1], " ".join(a[2:]))
        print("تم. على جهاز الفرع اضبط:\n  ERP_NODE_ID=%s\n  ERP_SYNC_KEY=%s\n  ERP_HQ_URL=<عنوان المركز الداخلي مثل http://IP:%s>" % (a[1], k, "ERP_INTERNAL_PORT"))
    elif c == "list":
        for n in nodesync.list_nodes():
            print(n["node_id"], n["label"], "آخر اتصال:", n["last_seen"] or "-")
    elif c == "remove" and len(a) == 2:
        nodesync.remove_node(a[1]); print("اتشال")
    else:
        print(__doc__); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
