import base64
from flask import Flask, request, redirect, send_file, abort
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

if __name__ == '__main__':
    # ローカル開発と本番環境で設定を分ける
    logging.info(f"Starting server on {HOST}:{PORT} with DEBUG={DEBUG}")
    logging.info(f"BASE_URL set to {BASE_URL}")

    # 利用可能なURLを出力
    for rule in app.url_map.iter_rules():
        logging.info(f"Endpoint: {rule.endpoint}, URL: {rule}")

    # 本番環境ではWSGIサーバー (例: Gunicorn, Waitress) を使用してください
    app.run(host=HOST, port=PORT, debug=DEBUG)
