# ベースイメージとして公式のPythonイメージを使用
FROM python:3.9-slim

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係をインストールするためにrequirements.txtをコピー
COPY requirements.txt requirements.txt

# 依存関係をインストール
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# アプリケーションのポート番号（新しいポートに変更）
EXPOSE 8081

# uvicorn で FastAPI サーバーを起動し、同時に push_worker も起動
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port 8081 & python push_worker.py"] 