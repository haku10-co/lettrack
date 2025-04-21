# push_worker.py
import time
import os
import queue
import gspread
import logging
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# server.py から共有キューをインポート
from server import EVENT_Q

# .envファイルがある場合は読み込む (スプレッドシートIDなどの設定)
load_dotenv(dotenv_path='.env.production')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - PushWorker - %(message)s')

# --- Google Sheets API 設定 ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'service_account.json') # 環境変数またはデフォルトファイル名
SHEET_ID = os.getenv("SHEET_ID") # 環境変数からスプレッドシートIDを取得

if not SHEET_ID:
    logging.error("SHEET_ID is not set in environment variables.")
    exit(1) # SHEET_ID がないと動作できない

if not os.path.exists(SERVICE_ACCOUNT_FILE):
    logging.error(f"Service account file not found: {SERVICE_ACCOUNT_FILE}")
    exit(1)

try:
    CREDS = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    gc = gspread.authorize(CREDS)
    spreadsheet = gc.open_by_key(SHEET_ID)
    emails_ws = spreadsheet.worksheet("emails")
    events_ws = spreadsheet.worksheet("events")
    logging.info(f"Successfully connected to Google Sheet ID: {SHEET_ID}")
except gspread.exceptions.SpreadsheetNotFound:
    logging.error(f"Spreadsheet not found. Check SHEET_ID: {SHEET_ID}")
    exit(1)
except gspread.exceptions.WorksheetNotFound as e:
    logging.error(f"Worksheet not found: {e}. Make sure 'emails' and 'events' sheets exist.")
    exit(1)
except Exception as e:
    logging.error(f"Failed to connect to Google Sheets: {e}")
    exit(1)
# --- Google Sheets API 設定ここまで ---

BATCH_INTERVAL = 60 # 処理間隔（秒）
MAX_DRAIN_COUNT = 500 # 一度に処理する最大イベント数

def drain(q: queue.SimpleQueue, n=MAX_DRAIN_COUNT):
    """キューから指定された最大数までイベントを取り出す"""
    batch = []
    for _ in range(n):
        try:
            batch.append(q.get_nowait())
        except queue.Empty:
            break
    return batch

def append_to_sheet(worksheet, rows):
    """Google Sheets に行を追加する (エラーハンドリング付き)"""
    if not rows:
        return
    try:
        worksheet.append_rows(rows, value_input_option="USER_ENTERED") # USER_ENTERED を使用してフォーマットを維持
        logging.info(f"Appended {len(rows)} rows to worksheet: {worksheet.title}")
    except gspread.exceptions.APIError as e:
        logging.error(f"Google Sheets API Error appending to {worksheet.title}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error appending to {worksheet.title}: {e}")

def run_worker():
    """メインのワーカーループ"""
    logging.info("Push worker started.")
    while True:
        try:
            time.sleep(BATCH_INTERVAL)
            rows = drain(EVENT_Q)
            if not rows:
                logging.debug("No events in queue, skipping.")
                continue

            logging.info(f"Drained {len(rows)} events from queue.")

            # emails シート用のデータ準備 (sent イベントのみ)
            sent_rows_for_sheet = []
            for r in rows:
                if r.get("status") == "sent":
                    # emails シートの列順: tracking_id, sent_ts, company_id, company_name, subject, body_snippet
                    sent_rows_for_sheet.append([
                        r.get("tracking_id", ""),
                        r.get("ts", ""),
                        r.get("company_id", ""),
                        r.get("company_name", ""),
                        r.get("subject", ""),
                        r.get("body_snippet", "")
                    ])

            # events シート用のデータ準備 (全イベント)
            event_rows_for_sheet = []
            for r in rows:
                # events シートの列順: ts, status, tracking_id, company_id, company_name, url, ip_address, user_agent, link_id
                event_rows_for_sheet.append([
                    r.get("ts", ""),
                    r.get("status", ""),
                    r.get("tracking_id", ""),
                    r.get("company_id", ""),
                    r.get("company_name", ""),
                    r.get("url", ""),
                    r.get("ip_address", ""), # IPアドレスを追加
                    r.get("user_agent", ""), # UserAgentを追加
                    r.get("link_id", "") # link_id を追加 (clickイベントのみ)
                ])

            # シートへの書き込み
            append_to_sheet(emails_ws, sent_rows_for_sheet)
            append_to_sheet(events_ws, event_rows_for_sheet)

        except KeyboardInterrupt:
            logging.info("Push worker stopped by user.")
            break
        except Exception as e:
            logging.error(f"An error occurred in the main loop: {e}", exc_info=True)
            # 重大なエラーでなければループを継続 (APIエラー等は append_to_sheet 内で処理)
            time.sleep(BATCH_INTERVAL) # エラー発生時も待機

if __name__ == "__main__":
    run_worker() 