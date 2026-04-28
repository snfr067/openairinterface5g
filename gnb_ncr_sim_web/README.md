# gNB × NCR Simulator

簡約版 gNB 與 NCR 模擬網站。

## 功能

- 單一 gNB 與單一 NCR
- 預設連線
- gNB 可發送 Periodic、Aperiodic、Semi-persistent 訊息給 NCR
- 發送時以對話框輸入數值欄位
- 前端 HTML / CSS / JS 分離
- 後端 Flask 單一 app.py
- 已移除 Link Quality 與 Live Metrics

## 啟動

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask
python3 app.py
```

瀏覽器開啟：

```text
http://127.0.0.1:5000
```
