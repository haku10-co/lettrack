from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from datetime import datetime
import queue, base64
import logging
import os # os をインポート
from dotenv import load_dotenv
from flask_cors import CORS
# import gspread # gspread は不要になったので削除またはコメントアウト
import requests # requests をインポート
import json # json をインポート

# .envファイルがある場合は読み込む
load_dotenv(dotenv_path='.env.production')

app = FastAPI()
CORS(app)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# 環境変数から設定を読み込む
PORT = int(os.environ.get('PORT', 8080))
HOST = os.environ.get('HOST', '0.0.0.0')
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8080')
TRACKING_DOMAIN = os.environ.get('TRACKING_DOMAIN', 'let-inc.net')
# --- GAS Web App 設定 ---
GAS_WEB_APP_URL = os.environ.get('GAS_WEB_APP_URL') # 環境変数から GAS Web App URL を読み込み
# --- GAS Web App 設定ここまで ---

# 1x1 透明GIFピクセルデータ (Base64エンコード)
# GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;
TRANSPARENT_GIF_DATA = base64.b64decode("R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==")

# --- GAS 連携 ---
if not GAS_WEB_APP_URL:
    logging.warning("GAS_WEB_APP_URL not configured. Data logging to GAS disabled.")

def send_data_to_gas(data_dict):
    """GAS Web AppにデータをPOSTする"""
    if GAS_WEB_APP_URL:
        try:
            headers = {'Content-Type': 'application/json'}
            # タイムアウトを設定 (例: 5秒)
            response = requests.post(GAS_WEB_APP_URL, headers=headers, data=json.dumps(data_dict), timeout=5)
            response.raise_for_status() # ステータスコードが 2xx でない場合に例外を発生させる
            logging.info(f"Successfully sent data to GAS: {data_dict}, Response: {response.text}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send data to GAS: {e}")
        except Exception as e:
             logging.error(f"An unexpected error occurred while sending data to GAS: {e}")
    else:
        logging.warning("GAS Web App URL not available. Skipping send.")
# --- GAS 連携ここまで ---

EVENT_Q = queue.SimpleQueue()          # push_worker と共有
EMAIL_MAP = {}                         # {tracking_id: (company_id, company_name)}

def enqueue(ev: dict):
    """イベントキューにデータを追加する"""
    logging.info(f"Enqueueing event: {ev}")
    EVENT_Q.put(ev)

@app.post("/register_email")
async def register_email(item: dict):
    """ローカル送信スクリプトからメール送信情報を登録する"""
    tracking_id = item.get("tracking_id")
    company_id = item.get("company_id")
    company_name = item.get("company_name")
    subject = item.get("subject")
    body_snippet = item.get("body_snippet", "") # body_snippet がない場合も考慮

    if not all([tracking_id, company_id, company_name, subject]):
        logging.warning(f"Missing data in /register_email: {item}")
        return {"ok": False, "error": "Missing required fields"}

    EMAIL_MAP[tracking_id] = (company_id, company_name)
    logging.info(f"Registered email: {tracking_id} for {company_name} ({company_id})")
    enqueue({
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z", # ISO 8601形式 (UTC)
        "status": "sent",
        "tracking_id": tracking_id,
        "company_id": company_id,
        "company_name": company_name,
        "subject": subject,
        "body_snippet": body_snippet[:120], # スニペットを120文字に制限
        "url": "" # sent イベントには URL はない
    })
    return {"ok": True}

@app.get("/open/{tid}")
async def track_open(tid: str, request: Request):
    """メール開封をトラッキングする"""
    cid, cname = EMAIL_MAP.get(tid, ("", ""))
    ip_address = request.client.host if request.client else "Unknown"
    user_agent = request.headers.get('User-Agent', 'Unknown')

    logging.info(f"Open tracked: tid={tid}, IP={ip_address}, User-Agent={user_agent}")

    enqueue({
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "status": "open",
        "tracking_id": tid,
        "company_id": cid,
        "company_name": cname,
        "url": "", # open イベントには URL はない
        "ip_address": ip_address, # 追加情報
        "user_agent": user_agent  # 追加情報
    })
    # キャッシュを防ぐヘッダーを追加
    headers = {
        'Cache-Control': 'no-cache, no-store, must-revalidate, private',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    return Response(content=TRANSPARENT_GIF_DATA, media_type="image/gif", headers=headers)

@app.get("/click/{tid}/{link_id}")
async def track_click(tid: str, link_id: str, request: Request): # link_id を str に変更
    """URLクリックをトラッキングし、元のURLにリダイレクトする"""
    url = request.query_params.get("url", "")
    cid, cname = EMAIL_MAP.get(tid, ("", ""))
    ip_address = request.client.host if request.client else "Unknown"
    user_agent = request.headers.get('User-Agent', 'Unknown')

    # URLがない場合のフォールバック先
    fallback_url = f"https://{TRACKING_DOMAIN}"

    logging.info(f"Click tracked: tid={tid}, link_id={link_id}, url={url}, IP={ip_address}, User-Agent={user_agent}")

    enqueue({
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "status": "click",
        "tracking_id": tid,
        "company_id": cid,
        "company_name": cname,
        "url": url,
        "ip_address": ip_address, # 追加情報
        "user_agent": user_agent,  # 追加情報
        "link_id": link_id # 追加情報
    })
    # URLが有効かどうかの簡単なチェック (より厳密な検証も可能)
    redirect_url = url if url and url.startswith(('http://', 'https://')) else fallback_url
    logging.info(f"Redirecting to: {redirect_url}")
    # 302 Found リダイレクト
    return RedirectResponse(redirect_url, status_code=302)

# 配信停止ページのHTMLテンプレート
UNSUBSCRIBE_HTML = '''
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>メール配信停止</title>
    <style>
        body {
            font-family: 'Helvetica Neue', Arial, sans-serif;
            background-color: #ffffff;
            color: #333333;
            line-height: 1.6;
            margin: 0;
            padding: 0;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            padding: 40px 20px;
            text-align: center;
        }
        .logo {
            margin-bottom: 30px;
            max-width: 200px;
            filter: brightness(0.9);
        }
        h1 {
            margin-bottom: 20px;
            color: #333;
            font-size: 24px;
        }
        p {
            margin-bottom: 25px;
            color: #666;
        }
        .email {
            font-weight: bold;
            color: #333;
        }
        .btn {
            display: inline-block;
            background-color: #4a6eb5;
            color: white;
            padding: 12px 24px;
            border-radius: 4px;
            text-decoration: none;
            font-weight: 500;
            margin: 20px 0;
            border: none;
            cursor: pointer;
            transition: background-color 0.3s ease;
        }
        .btn:hover {
            background-color: #3a5a95;
        }
        .success-message {
            display: none;
            background-color: #e8f5e9;
            border: 1px solid #c8e6c9;
            padding: 15px;
            border-radius: 4px;
            margin-top: 20px;
        }
        .footer {
            margin-top: 40px;
            font-size: 13px;
            color: #999;
        }
    </style>
</head>
<body>
    <div class="container">
        <img src="/let_logo" alt="LET Logo" class="logo">
        <h1>メール配信停止</h1>
        <p>以下のメールアドレスへの配信を停止します：</p>
        <p class="email">{{ email }}</p>
        
        <div id="unsubscribe-form">
            <p>配信停止を希望される場合は、以下のボタンをクリックしてください。</p>
            <button class="btn" id="unsubscribe-btn">配信を停止する</button>
        </div>
        
        <div id="success-message" class="success-message">
            <p>メール配信の停止が完了しました。</p>
            <p>ご利用ありがとうございました。</p>
        </div>
        
        <div class="footer">
            <p>ご質問がございましたら、サポートまでお問い合わせください。</p>
        </div>
    </div>
    
    <script>
        document.getElementById('unsubscribe-btn').addEventListener('click', function() {
            // API呼び出し
            fetch('/api/unsubscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    email: '{{ email }}',
                    tracking_id: '{{ tracking_id }}'
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // フォームを非表示にし、成功メッセージを表示
                    document.getElementById('unsubscribe-form').style.display = 'none';
                    document.getElementById('success-message').style.display = 'block';
                } else {
                    alert('エラーが発生しました: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('エラーが発生しました。しばらく経ってからもう一度お試しください。');
            });
        });
    </script>
</body>
</html>
'''

@app.route('/let_logo')
def let_logo():
    """LETロゴを提供するエンドポイント"""
    try:
        with open('ChatGPT Image 2025年4月4日 21_03_05 1.png', 'rb') as f:
            logo_data = f.read()
        return send_file(
            io.BytesIO(logo_data),
            mimetype='image/png'
        )
    except Exception as e:
        logging.error(f"Error serving logo: {e}")
        abort(500, description="Could not load logo")

@app.route('/unsubscribe/<tracking_id>')
def unsubscribe_page(tracking_id):
    """配信停止ページを表示するエンドポイント"""
    email = request.args.get('email')
    if not email:
        logging.warning(f"Unsubscribe attempted with no email: tracking_id={tracking_id}")
        abort(400, description="Missing 'email' parameter")
    
    user_agent = request.headers.get('User-Agent', 'Unknown')
    ip_address = request.remote_addr
    timestamp = datetime.now().isoformat()
    
    logging.info(f"Unsubscribe page visited: tracking_id={tracking_id}, email={email}, IP={ip_address}, User-Agent={user_agent}")
    
    # GASにページアクセスを記録
    gas_data = {
        "timestamp": timestamp,
        "type": "unsubscribe_view",
        "trackingId": tracking_id,
        "email": email,
        "ipAddress": ip_address,
        "userAgent": user_agent
    }
    send_data_to_gas(gas_data)
    
    return render_template_string(UNSUBSCRIBE_HTML, email=email, tracking_id=tracking_id)

@app.route('/api/unsubscribe', methods=['POST'])
def process_unsubscribe():
    """配信停止処理を行うAPIエンドポイント"""
    try:
        data = request.json
        email = data.get('email')
        tracking_id = data.get('tracking_id')
        
        if not email or not tracking_id:
            return jsonify({"success": False, "message": "必要なパラメータが不足しています"}), 400
        
        user_agent = request.headers.get('User-Agent', 'Unknown')
        ip_address = request.remote_addr
        timestamp = datetime.now().isoformat()
        
        logging.info(f"Unsubscribe requested: tracking_id={tracking_id}, email={email}, IP={ip_address}, User-Agent={user_agent}")
        
        # GASに配信停止リクエストを記録
        gas_data = {
            "timestamp": timestamp,
            "type": "unsubscribe_confirm",
            "trackingId": tracking_id,
            "email": email,
            "ipAddress": ip_address,
            "userAgent": user_agent
        }
        send_data_to_gas(gas_data)
        
        # ここで実際の配信停止処理を行う
        # 実際のユーザーDBへの操作はこのコードには含まれていないため、
        # GASが配信停止リクエストを処理することを前提としています
        
        return jsonify({"success": True})
    except Exception as e:
        logging.error(f"Error processing unsubscribe: {e}")
        return jsonify({"success": False, "message": "内部エラーが発生しました"}), 500

if __name__ == '__main__':
    # ローカル開発と本番環境で設定を分ける
    logging.info(f"Starting server on {HOST}:{PORT} with DEBUG={DEBUG}")
    logging.info(f"BASE_URL set to {BASE_URL}")

    # 利用可能なURLを出力
    for rule in app.url_map.iter_rules():
        logging.info(f"Endpoint: {rule.endpoint}, URL: {rule}")

    # 本番環境ではWSGIサーバー (例: Gunicorn, Waitress) を使用してください
    app.run(host=HOST, port=PORT, debug=DEBUG)
