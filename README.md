# メールトラッキングサーバー

このサーバーはメールの開封トラッキングとURLクリックトラッキングを実装したシンプルなFlaskアプリケーションです。

## 機能

- 開封トラッキング：透明GIF画像を使用したメール開封の検出
- クリックトラッキング：リンククリックのトラッキングとリダイレクト

## 環境設定

設定を行うには `.env` ファイルを作成します：

```
# .env.example をコピーして使用してください
cp .env.example .env
```

環境変数：

- `PORT`: サーバーポート (デフォルト: 8080)
- `HOST`: ホスト (デフォルト: 0.0.0.0)
- `DEBUG`: デバッグモード (True/False)
- `BASE_URL`: トラッキングURLのベースURL (例: https://track.let-inc.net)

## 開発環境のセットアップ

```
# Python仮想環境の作成と有効化
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存関係のインストール
pip install -r requirements.txt

# 開発サーバーの起動
python server.py
```

## 本番環境へのデプロイ

本番環境では、以下の設定を行います：

1. 環境変数の設定
```
# .env.production を作成
PORT=8080  # または必要なポート
HOST=0.0.0.0
DEBUG=False
BASE_URL=https://track.let-inc.net  # 本番用ドメイン
```

2. Gunicornを使用したサーバー起動
```
gunicorn -w 4 -b 0.0.0.0:8080 server:app
```

## 使用例

### 開封トラッキング

メールHTMLに以下のタグを追加します：
```html
<img src="https://track.let-inc.net/open/12345" width="1" height="1" alt="">
```

### クリックトラッキング

リンクを以下のように変更します：
```html
<a href="https://track.let-inc.net/click/12345/link1?url=https://example.com">リンクテキスト</a>
```

## ライセンス

All rights reserved.
