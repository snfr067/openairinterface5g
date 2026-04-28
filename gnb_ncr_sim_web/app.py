from flask import Flask, jsonify, render_template, request
from datetime import datetime
from pathlib import Path
import atexit
import os
import re
import signal
import subprocess


app = Flask(__name__)


# ============================================================
# 路徑設定
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OAI_DIR = BASE_DIR.parent

LOG_DIR = BASE_DIR / "runtime_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 啟動 gNB / UE 腳本設定
# ============================================================

SCRIPT_COMMANDS = [
    {
        "name": "gNB",
        "path": OAI_DIR / "gnb_cmd.sh",
        "log": LOG_DIR / "gnb_cmd.log",
    },
    {
        "name": "UE",
        "path": OAI_DIR / "ue_cmd.sh",
        "log": LOG_DIR / "ue_cmd.log",
    },
]

started_processes = []
oai_started = False


# ============================================================
# UE RNTI / ID 擷取設定
# ============================================================

UE_RNTI_PATTERNS = [
    re.compile(r"\bUE\s+RNTI\s+([0-9a-fA-F]+)\b"),
    re.compile(r"\bUE\s+([0-9a-fA-F]+)\s*:\s+"),
]

UE_RNTI_SCAN_FILES = [
    LOG_DIR / "gnb_cmd.log",
    LOG_DIR / "ue_cmd.log",
    Path("/tmp/gnb.log"),
]

MAX_LOG_TAIL_BYTES = 1024 * 1024


def start_oai_scripts_once():
    """
    啟動 openairinterface5g/ 底下的 gnb_cmd.sh 與 ue_cmd.sh。
    使用 subprocess.Popen 非阻塞啟動，避免 Flask 被卡住。
    """

    global oai_started

    if oai_started:
        print("[WEB][BOOT] OAI scripts already started, skip.")
        return

    oai_started = True

    for item in SCRIPT_COMMANDS:
        script_path = item["path"]
        log_path = item["log"]

        if not script_path.exists():
            print(f"[WEB][BOOT] Skip {item['name']}: script not found: {script_path}")
            continue

        if not os.access(script_path, os.X_OK):
            print(f"[WEB][BOOT] {item['name']} script is not executable, run with bash anyway: {script_path}")

        try:
            log_file = open(log_path, "a", buffering=1, encoding="utf-8")

            print(f"[WEB][BOOT] Starting {item['name']}: {script_path}")
            print(f"[WEB][BOOT] Log file: {log_path}")

            proc = subprocess.Popen(
                ["bash", str(script_path)],
                cwd=str(OAI_DIR),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )

            started_processes.append(
                {
                    "name": item["name"],
                    "process": proc,
                    "log_file": log_file,
                    "log_path": log_path,
                }
            )

            print(f"[WEB][BOOT] {item['name']} started, pid={proc.pid}")

        except Exception as exc:
            print(f"[WEB][BOOT] Failed to start {item['name']}: {exc}")


def stop_oai_scripts():
    """
    Flask 關閉時，停止由本 app.py 啟動的 gNB / UE process group。
    """

    for item in started_processes:
        name = item["name"]
        proc = item["process"]

        if proc.poll() is None:
            print(f"[WEB][STOP] Stopping {name}, pid={proc.pid}")

            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as exc:
                print(f"[WEB][STOP] Failed to stop {name}: {exc}")

        try:
            item["log_file"].close()
        except Exception:
            pass


atexit.register(stop_oai_scripts)


# ============================================================
# Demo 狀態資料
# ============================================================

state = {
    "nodes": {
        "gnb": {
            "id": "gNB-001",
            "name": "gNB",
            "role": "Base Station",
            "status": "online",
            "ip": "127.0.0.1",
        },
        "ncr": {
            "id": "NCR-001",
            "name": "NCR",
            "role": "Network-Controlled Repeater",
            "status": "connected",
            "ip": "127.0.0.1",
            "ue_id": None,
            "ue_id_updated_at": None,
        },
    },
    "link": {
        "source": "gNB-001",
        "target": "NCR-001",
        "connected": True,
    },
    "messages": [],
    "rules": [],
}


MESSAGE_TYPES = {
    "Periodic",
    "Aperiodic",
    "Semi-persistent",
}

NUMERIC_FIELDS = [
    "resource_id",
    "rsrc_id",
    "beam",
    "slotPeriod",
    "slotOffset",
    "symbol_offset",
    "duration_in_symbols",
    "ref_scs",
]


# ============================================================
# 工具函式
# ============================================================

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_log_tail(path: Path, max_bytes: int = MAX_LOG_TAIL_BYTES) -> str:
    """
    只讀 log 尾端，避免 log 很大時拖慢網頁。
    """

    if not path.exists() or not path.is_file():
        return ""

    try:
        with open(path, "rb") as file_obj:
            file_obj.seek(0, os.SEEK_END)
            file_size = file_obj.tell()
            start_pos = max(0, file_size - max_bytes)
            file_obj.seek(start_pos)
            data = file_obj.read()
        return data.decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"[WEB][UE-ID] Failed to read log {path}: {exc}")
        return ""


def extract_last_ue_rnti_from_text(text: str):
    """
    從 OAI log 裡抓 UE RNTI。

    支援範例：
    UE RNTI 371a CU-UE-ID 1 in-sync ...
    UE 371a: dlsch_rounds ...
    UE 371a: MAC: TX ...
    """

    matches = []

    for pattern in UE_RNTI_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1).lower()
            matches.append((match.start(), value))

    if not matches:
        return None

    matches.sort(key=lambda item: item[0])
    return matches[-1][1]


def refresh_ncr_ue_id_from_logs():
    """
    掃描 gNB/UE log，抓最後出現的 UE RNTI，更新到 NCR 狀態。
    """

    candidates = []

    for path in UE_RNTI_SCAN_FILES:
        text = read_log_tail(path)
        if not text:
            continue

        ue_id = extract_last_ue_rnti_from_text(text)
        if ue_id:
            try:
                mtime = path.stat().st_mtime
            except Exception:
                mtime = 0

            candidates.append(
                {
                    "ue_id": ue_id,
                    "path": str(path),
                    "mtime": mtime,
                }
            )

    if not candidates:
        return state["nodes"]["ncr"].get("ue_id")

    candidates.sort(key=lambda item: item["mtime"])
    latest = candidates[-1]

    old_ue_id = state["nodes"]["ncr"].get("ue_id")
    new_ue_id = latest["ue_id"]

    if old_ue_id != new_ue_id:
        print(f"[WEB][UE-ID] NCR UE ID updated: {old_ue_id} -> {new_ue_id} from {latest['path']}")

    state["nodes"]["ncr"]["ue_id"] = new_ue_id
    state["nodes"]["ncr"]["ue_id_updated_at"] = now_text()
    state["nodes"]["ncr"]["ue_id_source_log"] = latest["path"]

    return new_ue_id


def read_params_from_request(raw):
    """
    同時支援兩種前端格式：

    格式 A：
    {
        "type": "Periodic",
        "params": {
            "resource_id": 0
        }
    }

    格式 B：
    {
        "type": "Periodic",
        "resource_id": 0
    }
    """

    if not isinstance(raw, dict):
        raise ValueError("payload must be an object")

    if isinstance(raw.get("params"), dict):
        return raw["params"]

    return raw


def parse_int_field(params, key):
    value = params.get(key)

    if value is None or value == "":
        raise ValueError(f"missing field: {key}")

    try:
        return int(value)
    except Exception:
        raise ValueError(f"field must be numeric: {key}")


def normalize_payload(raw):
    if not isinstance(raw, dict):
        raise ValueError("payload must be an object")

    message_type = raw.get("type")

    if message_type not in MESSAGE_TYPES:
        raise ValueError("invalid message type")

    params_source = read_params_from_request(raw)

    params = {}

    for field in NUMERIC_FIELDS:
        params[field] = parse_int_field(params_source, field)

    return message_type, params


def make_rule_from_message(message):
    params = message["params"]

    return {
        "id": len(state["rules"]) + 1,
        "created_at": message["time"],
        "owner": state["nodes"]["ncr"]["id"],
        "source_message_id": message["id"],
        "type": message["type"],
        "status": "active",
        "params": params,
        "summary": (
            f"{message['type']} | "
            f"resource_id={params['resource_id']} | "
            f"rsrc={params['rsrc_id']} | "
            f"beam={params['beam']} | "
            f"period={params['slotPeriod']} | "
            f"offset={params['slotOffset']} | "
            f"sym={params['symbol_offset']} | "
            f"dur={params['duration_in_symbols']} | "
            f"ref_scs={params['ref_scs']}"
        ),
    }


def get_runtime_process_status():
    process_status = []

    for item in started_processes:
        proc = item["process"]

        if proc.poll() is None:
            status = "running"
            return_code = None
        else:
            status = "stopped"
            return_code = proc.returncode

        process_status.append(
            {
                "name": item["name"],
                "pid": proc.pid,
                "status": status,
                "return_code": return_code,
                "log_path": str(item["log_path"]),
            }
        )

    return process_status


# ============================================================
# Web Routes
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# API Routes
# ============================================================

@app.route("/api/state", methods=["GET"])
def get_state():
    refresh_ncr_ue_id_from_logs()
    return jsonify(state)


@app.route("/api/send", methods=["POST"])
def send_message():
    """
    Demo 流程：
    1. 前端送出 Periodic / Aperiodic / Semi-persistent。
    2. gNB 建立 forwarding message。
    3. NCR 接收後保存成 rule。
    4. 回傳更新後的 state 給前端刷新列表。
    """

    refresh_ncr_ue_id_from_logs()

    raw = request.get_json(silent=True)

    try:
        message_type, params = normalize_payload(raw)
    except ValueError as exc:
        return jsonify(
            {
                "ok": False,
                "error": str(exc),
            }
        ), 400

    message = {
        "id": len(state["messages"]) + 1,
        "time": now_text(),
        "from": state["nodes"]["gnb"]["id"],
        "to": state["nodes"]["ncr"]["id"],
        "type": message_type,
        "params": params,
        "status": "delivered",
    }

    rule = make_rule_from_message(message)

    state["messages"].insert(0, message)
    state["rules"].insert(0, rule)

    state["messages"] = state["messages"][:80]
    state["rules"] = state["rules"][:80]

    return jsonify(
        {
            "ok": True,
            "message": message,
            "rule": rule,
            "state": state,
        }
    )


@app.route("/api/messages", methods=["GET"])
def get_messages():
    refresh_ncr_ue_id_from_logs()

    return jsonify(
        {
            "ok": True,
            "messages": state["messages"],
        }
    )


@app.route("/api/rules", methods=["GET"])
def get_rules():
    refresh_ncr_ue_id_from_logs()

    return jsonify(
        {
            "ok": True,
            "rules": state["rules"],
        }
    )


@app.route("/api/runtime", methods=["GET"])
def get_runtime_status():
    refresh_ncr_ue_id_from_logs()

    return jsonify(
        {
            "ok": True,
            "oai_started": oai_started,
            "ncr_ue_id": state["nodes"]["ncr"].get("ue_id"),
            "processes": get_runtime_process_status(),
        }
    )


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    start_oai_scripts_once()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False,
    )
