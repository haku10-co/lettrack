import base64
from flask import Flask, request, redirect, send_file, abort, render_template_string, jsonify
import io
import logging
from urllib.parse import urlparse, urlunparse
import os
from dotenv import load_dotenv
from flask_cors import CORS
# import gspread # gspread は不要になったので削除またはコメントアウト
from datetime import datetime
import requests # requests をインポート
import json # json をインポート

# .envファイルがある場合は読み込む
load_dotenv(dotenv_path='.env.production')

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# 環境変数から設定を読み込む
PORT = int(os.environ.get('PORT', 8080))
HOST = os.environ.get('HOST', '0.0.0.0')
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8080')
TRACKING_DOMAIN = os.environ.get('TRACKING_DOMAIN', 'localhost:8080')
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

@app.route('/open/<tracking_id>')
def track_open(tracking_id):
    """
    メール開封をトラッキングするエンドポイント
    """
    user_agent = request.headers.get('User-Agent', 'Unknown')
    ip_address = request.remote_addr
    timestamp = datetime.now().isoformat() # 現在時刻を取得

    logging.info(f"Opened: tracking_id={tracking_id}, IP={ip_address}, User-Agent={user_agent}")

    # --- GAS に送信するデータを作成 (辞書形式) ---
    gas_data = {
        "timestamp": timestamp,
        "type": "open",
        "trackingId": tracking_id,
        "linkId": "", # open の場合は空
        "originalUrl": "", # open の場合は空
        "ipAddress": ip_address,
        "userAgent": user_agent
    }
    send_data_to_gas(gas_data)
    # --- GAS 送信ここまで ---

    return send_file(
        io.BytesIO(TRANSPARENT_GIF_DATA),
        mimetype='image/gif'
    )

# トラッキングURLを生成するヘルパー関数
def get_tracking_url(tracking_type, tracking_id, link_id=None, original_url=None):
    """
    トラッキング用URLを生成する
    """
    if tracking_type == 'open':
        return f"{BASE_URL}/open/{tracking_id}"
    elif tracking_type == 'click' and link_id and original_url:
        return f"{BASE_URL}/click/{tracking_id}/{link_id}?url={original_url}"
    return None

def create_unsubscribe_url(email, tracking_id):
    """配信停止用のURLを生成する"""
    return f"https://{TRACKING_DOMAIN}/unsubscribe/{tracking_id}?email={email}"

@app.route('/click/<tracking_id>/<link_id>')
def track_click(tracking_id, link_id):
    """
    URLクリックをトラッキングし、元のURLにリダイレクトするエンドポイント
    """
    original_url = request.args.get('url')
    if not original_url:
        logging.warning(f"Click attempted with no URL: tracking_id={tracking_id}, link_id={link_id}")
        abort(400, description="Missing 'url' parameter")

    # URLの基本的な検証 (より厳密な検証が必要な場合もあります)
    try:
        parsed_url = urlparse(original_url)
        if not parsed_url.scheme or not parsed_url.netloc:
             raise ValueError("Invalid URL structure")
        # URLを再構築して正規化 (例: 不要なフラグメントを削除するなど)
        original_url = urlunparse(parsed_url)
    except ValueError as e:
        logging.error(f"Invalid URL format: {original_url}, Error: {e}")
        abort(400, description="Invalid 'url' parameter format")

    user_agent = request.headers.get('User-Agent', 'Unknown')
    ip_address = request.remote_addr
    timestamp = datetime.now().isoformat() # 現在時刻を取得

    logging.info(f"Clicked: tracking_id={tracking_id}, link_id={link_id}, url={original_url}, IP={ip_address}, User-Agent={user_agent}")

    # --- GAS に送信するデータを作成 (辞書形式) ---
    gas_data = {
        "timestamp": timestamp,
        "type": "click",
        "trackingId": tracking_id,
        "linkId": link_id,
        "originalUrl": original_url,
        "ipAddress": ip_address,
        "userAgent": user_agent
    }
    send_data_to_gas(gas_data)
    # --- GAS 送信ここまで ---

    # 302 Found リダイレクト
    return redirect(original_url, code=302)

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
