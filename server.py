import base64
from flask import Flask, request, redirect, send_file, abort
import io
import logging
from urllib.parse import urlparse, urlunparse
import os
from dotenv import load_dotenv

# .envファイルがある場合は読み込む
load_dotenv(dotenv_path='.env.production')  # 明示的に.env.productionを指定

app = Flask(__name__)

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# 環境変数から設定を読み込む
# デフォルト値はローカル開発用
PORT = int(os.environ.get('PORT', 8080))
HOST = os.environ.get('HOST', '0.0.0.0')
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8080')

# 1x1 透明GIFピクセルデータ (Base64エンコード)
# GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;
TRANSPARENT_GIF_DATA = base64.b64decode("R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==")

@app.route('/open/<tracking_id>')
def track_open(tracking_id):
    """
    メール開封をトラッキングするエンドポイント
    """
    user_agent = request.headers.get('User-Agent', 'Unknown')
    ip_address = request.remote_addr
    logging.info(f"Opened: tracking_id={tracking_id}, IP={ip_address}, User-Agent={user_agent}")
    # ここでデータベースなどに記録する処理を追加できます
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
    logging.info(f"Clicked: tracking_id={tracking_id}, link_id={link_id}, url={original_url}, IP={ip_address}, User-Agent={user_agent}")
    # ここでデータベースなどに記録する処理を追加できます

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
