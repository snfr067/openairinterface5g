from flask import Flask, jsonify, render_template, request
from datetime import datetime
from pathlib import Path
import atexit
import os
import re
import signal
import subprocess
import telnetlib
import time
import traceback

app = Flask(__name__)


# ============================================================
# 路徑設定
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OAI_DIR = BASE_DIR.parent

LOG_DIR = BASE_DIR / "runtime_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
TELNET_COMMAND_LOG = LOG_DIR / "telnet_commands.log"


# ============================================================
# Telnet 設定
# ============================================================

TELNET_HOST = "127.0.0.1"
TELNET_PORT = 16888
TELNET_TIMEOUT = 2


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
            "ue_id_source_log": None,
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

TELNET_TYPE_MAP = {
    "Periodic": "periodic",
    "Aperiodic": "aperiodic",
    "Semi-persistent": "semi-persistent",
}

NUMERIC_FIELDS = [
    "rsrc_id",
    "beam",
    "slotPeriod",
    "slotOffset",
    "symbol_offset",
    "duration_in_symbols",
    "ref_scs",
]


def append_telnet_log(text):
    """
    強制把 telnet 發送紀錄寫到網站自己的 log。
    用來確認到底有沒有執行到發送流程。
    """

    line = f"[{now_text()}] {text}\n"

    print(line, end="", flush=True)

    try:
        with open(TELNET_COMMAND_LOG, "a", encoding="utf-8") as log_file:
            log_file.write(line)
            log_file.flush()
    except Exception as exc:
        print(f"[WEB][TELNET][LOG-ERROR] {type(exc).__name__}: {exc}", flush=True)

# ============================================================
# 啟動 / 關閉 OAI scripts
# ============================================================

def reset_oai_runtime_logs_on_start():
    """
    網站啟動時先刪掉 gNB / UE 的舊 log。
    只刪 SCRIPT_COMMANDS 裡設定的 gnb_cmd.log 與 ue_cmd.log。
    """

    for item in SCRIPT_COMMANDS:
        log_path = item["log"]

        try:
            if log_path.exists():
                log_path.unlink()
                print(f"[WEB][BOOT] Removed old {item['name']} log: {log_path}", flush=True)
        except Exception as exc:
            print(
                f"[WEB][BOOT] Failed to remove old {item['name']} log {log_path}: {type(exc).__name__}: {exc}",
                flush=True,
            )

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
# 工具函式
# ============================================================

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def next_resource_id():
    """
    resource id 永遠由目前規則數 + 1 自動產生。
    """
    return len(state["rules"]) + 1


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
        if not ue_id:
            continue

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
    支援前端格式：
    {
        "type": "Periodic",
        "params": {
            "resource_id": 1,
            "rsrc_id": 0,
            ...
        }
    }

    也支援扁平格式：
    {
        "type": "Periodic",
        "resource_id": 1,
        "rsrc_id": 0,
        ...
    }

    注意：
    resource_id 會由後端依目前規則數 + 1 自動覆蓋。
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

    params = {
        "resource_id": next_resource_id(),
    }

    for field in NUMERIC_FIELDS:
        params[field] = parse_int_field(params_source, field)

    return message_type, params


def build_telnet_command(message_type, params, ue_id):
    """
    建立實際送到 gNB telnet 的 NCR 指令。

    範例：
    ncr periodic mod=0 rnti=0x371a refscs=1 set=1 rsrc=0 beam=7 period=20 offset=0 sym=2 dur=4
    """

    telnet_type = TELNET_TYPE_MAP[message_type]

    return (
        f"ncr {telnet_type} "
        f"mod=0 "
        f"rnti=0x{ue_id} "
        f"refscs={params['ref_scs']} "
        f"set={params['resource_id']} "
        f"rsrc={params['rsrc_id']} "
        f"beam={params['beam']} "
        f"period={params['slotPeriod']} "
        f"offset={params['slotOffset']} "
        f"sym={params['symbol_offset']} "
        f"dur={params['duration_in_symbols']}"
    )


def send_telnet_command(command):
    """
    把指令送到 gNB telnet，並強制留下送出紀錄。
    """

    append_telnet_log(f"[SEND-BEGIN] host={TELNET_HOST} port={TELNET_PORT} command={command}")

    chunks = []

    try:
        with telnetlib.Telnet(TELNET_HOST, TELNET_PORT, TELNET_TIMEOUT) as tn:
            append_telnet_log("[CONNECTED] telnet connected")

            try:
                banner = tn.read_very_eager().decode(errors="ignore")
            except EOFError:
                banner = ""

            if banner:
                chunks.append("[banner]\n" + banner)
                append_telnet_log(f"[BANNER] {banner.strip()}")

            tn.write(command.encode("utf-8") + b"\n")
            append_telnet_log(f"[WRITE-DONE] {command}")

            for _ in range(8):
                time.sleep(0.2)

                try:
                    data = tn.read_very_eager()
                except EOFError:
                    append_telnet_log("[READ-EOF]")
                    break

                if data:
                    decoded = data.decode(errors="ignore")
                    chunks.append(decoded)
                    append_telnet_log(f"[READ] {decoded.strip()}")

        result = "".join(chunks).strip() or "(沒有收到 telnet 回覆)"
        append_telnet_log(f"[SEND-END] result={result}")

        return result

    except Exception as exc:
        append_telnet_log(f"[SEND-ERROR] {type(exc).__name__}: {exc}")
        append_telnet_log(traceback.format_exc())
        raise

def telnet_result_is_success(result: str) -> bool:
    """
    判斷 telnet 指令是否可視為成功。

    原則：
    1. telnet exception 會在 send_message() 裡直接擋掉。
    2. telnet 有回明顯錯誤字串時，不寫入 message/rule。
    3. OAI telnet 有時候沒有回覆，因此「沒有收到 telnet 回覆」不直接當錯。
    """

    text = (result or "").lower()

    error_keywords = [
        "http/1.1 400",
        "bad request",
        "error",
        "failed",
        "failure",
        "invalid",
        "missing",
        "unsupported",
        "not found",
        "cannot",
        "unknown",
    ]

    return not any(keyword in text for keyword in error_keywords)


def make_rule_from_message(message):
    params = message["params"]

    return {
        "id": params["resource_id"],
        "created_at": message["time"],
        "owner": state["nodes"]["ncr"]["id"],
        "source_message_id": message["id"],
        "type": message["type"],
        "status": "active",
        "telnet_command": message["telnet_command"],
        "telnet_result": message["telnet_result"],
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

    state["next_resource_id"] = next_resource_id()

    return jsonify(state)


@app.route("/api/send", methods=["POST"])
def send_message():
    """
    流程：
    1. 前端送出 Periodic / Aperiodic / Semi-persistent。
    2. 後端自動指定 resource_id = 目前規則數 + 1。
    3. 從 log 抓 NCR UE ID。
    4. 組 telnet 指令送到 127.0.0.1:9090。
    5. 只有 telnet 成功時才新增 message 與 rule。
    6. telnet 失敗時直接回錯誤，不寫入規則列表；下一次 resource_id 仍維持同一個序號。
    """

    ue_id = refresh_ncr_ue_id_from_logs()

    if not ue_id:
        return jsonify(
            {
                "ok": False,
                "error": "尚未抓到 NCR 的 UE ID，請確認 gNB / UE log 已出現 UE RNTI。",
            }
        ), 400

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

    telnet_command = build_telnet_command(message_type, params, ue_id)

    try:
        telnet_result = send_telnet_command(telnet_command)
    except Exception as exc:
        return jsonify(
            {
                "ok": False,
                "error": f"telnet 發送失敗：{type(exc).__name__}: {exc}",
                "telnet_command": telnet_command,
                "state": state,
            }
        ), 502

    if not telnet_result_is_success(telnet_result):
        return jsonify(
            {
                "ok": False,
                "error": "telnet 指令被 gNB 拒絕，未寫入規則列表。",
                "telnet_command": telnet_command,
                "telnet_result": telnet_result,
                "state": state,
            }
        ), 400

    message = {
        "id": len(state["messages"]) + 1,
        "time": now_text(),
        "from": state["nodes"]["gnb"]["id"],
        "to": state["nodes"]["ncr"]["id"],
        "type": message_type,
        "params": params,
        "rnti": f"0x{ue_id}",
        "telnet_command": telnet_command,
        "telnet_result": telnet_result,
        "status": "delivered",
    }

    rule = make_rule_from_message(message)

    state["messages"].insert(0, message)
    state["rules"].insert(0, rule)

    state["messages"] = state["messages"][:80]
    state["rules"] = state["rules"][:80]
    state["next_resource_id"] = next_resource_id()

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
            "next_resource_id": next_resource_id(),
            "processes": get_runtime_process_status(),
        }
    )


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    reset_oai_runtime_logs_on_start()
    start_oai_scripts_once()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False,
    )
