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

# アプリケーションのポート番号（必要に応じて変更）
EXPOSE 8080

# アプリケーションを実行
CMD ["python", "server.py"] 