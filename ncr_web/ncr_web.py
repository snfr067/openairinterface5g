from flask import Flask, request, render_template_string
import telnetlib
import html

app = Flask(__name__)

TELNET_HOST = "127.0.0.1"
TELNET_PORT = 9090
TELNET_TIMEOUT = 2

PAGE = """
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NCR gNB Control</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; background: #f6f7fb; }
    .wrap { max-width: 900px; margin: 0 auto; }
    .card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 12px rgba(0,0,0,.08); }
    h1 { margin-top: 0; }
    textarea { width: 100%; min-height: 120px; font-family: monospace; font-size: 15px; padding: 12px; box-sizing: border-box; }
    input[type=text], input[type=number] { width: 100%; padding: 10px; box-sizing: border-box; }
    button { background: #0b57d0; color: white; border: 0; border-radius: 8px; padding: 10px 18px; font-size: 15px; cursor: pointer; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
    .label { margin-bottom: 6px; font-weight: 600; }
    .result { white-space: pre-wrap; background: #0f172a; color: #e5e7eb; padding: 14px; border-radius: 8px; min-height: 120px; font-family: monospace; }
    .hint { color: #475569; font-size: 14px; }
    .ok { color: #166534; }
    .err { color: #b91c1c; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>NCR gNB 控制頁面</h1>
      <p class="hint">這個頁面只是把您輸入的字串送到 gNB telnet（預設 127.0.0.1:9090），效果等同您手動 telnet 後輸入指令。</p>

      <form method="post" action="/send">
        <div class="row">
          <div>
            <div class="label">Telnet Host</div>
            <input type="text" name="host" value="{{ host }}">
          </div>
          <div>
            <div class="label">Telnet Port</div>
            <input type="number" name="port" value="{{ port }}">
          </div>
        </div>

        <div class="label">Command</div>
        <textarea name="command">{{ command }}</textarea>
        <br><br>
        <button type="submit">送出到 gNB</button>
      </form>

      {% if status %}
        <hr>
        <div class="label">結果</div>
        <div class="{{ 'ok' if success else 'err' }}"><strong>{{ status }}</strong></div>
        <br>
        <div class="result">{{ result }}</div>
      {% endif %}
    </div>
  </div>
</body>
</html>
"""


def send_telnet_command(host: str, port: int, command: str) -> str:
    # 使用 telnetlib，避免自己處理 telnet 細節
    with telnetlib.Telnet(host, port, TELNET_TIMEOUT) as tn:
        try:
            banner = tn.read_very_eager().decode(errors="ignore")
        except EOFError:
            banner = ""

        tn.write(command.encode() + b"\n")

        chunks = []
        if banner:
            chunks.append("[banner]\n" + banner)

        # 連續讀幾次，收集 telnet 回覆
        for _ in range(6):
            try:
                data = tn.read_until(b"\n", timeout=0.4)
            except EOFError:
                break
            if not data:
                break
            chunks.append(data.decode(errors="ignore"))

        return "".join(chunks).strip() or "(沒有收到 telnet 回覆)"


@app.route("/", methods=["GET"])
def index():
    default_cmd = "ncr periodic mod=0 rnti=0x74d0 set=0 rsrc=0 beam=7 period=20 offset=0 sym=2 dur=4"
    return render_template_string(PAGE, host=TELNET_HOST, port=TELNET_PORT, command=default_cmd,
                                  status=None, result=None, success=False)


@app.route("/send", methods=["POST"])
def send():
    host = request.form.get("host", TELNET_HOST).strip() or TELNET_HOST
    port_raw = request.form.get("port", str(TELNET_PORT)).strip() or str(TELNET_PORT)
    command = request.form.get("command", "").strip()

    try:
        port = int(port_raw)
    except ValueError:
        return render_template_string(PAGE, host=host, port=port_raw, command=command,
                                      status="Port 格式錯誤", result="port 必須是數字", success=False)

    if not command:
        return render_template_string(PAGE, host=host, port=port, command=command,
                                      status="Command 不可為空", result="請輸入 NCR 指令", success=False)

    try:
        result = send_telnet_command(host, port, command)
        status = "已送到 gNB telnet"
        success = True
    except Exception as e:
        status = "送出失敗"
        result = f"{type(e).__name__}: {e}"
        success = False

    return render_template_string(PAGE, host=host, port=port, command=command,
                                  status=status, result=result, success=success)


if __name__ == "__main__":
    # 先只綁 127.0.0.1，避免直接暴露到外網
    app.run(host="0.0.0.0", port=8088, debug=False)

