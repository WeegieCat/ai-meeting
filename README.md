# ai-meeting

## セットアップ

```bash
uv sync
cp .env.example .env   # 各APIキー、FISH_VOICE_ID、ANAM_AVATAR_ID を設定
uv run main.py         # http://localhost:7860/client を開く
```

## 音声・映像のルーティング

Pipecatの入出力は「ローカルのWebRTCクライアント(ブラウザ)」です。ブラウザ側でデバイスを選びます。

| 経路 | 設定 |
|---|---|
| 面接官の声 → Pipecat | Meet(Chrome)のスピーカー出力 = 仮想デバイスA、WebRTCクライアントのマイク = 仮想デバイスA の出力側 |
| Pipecat → Meetのマイク | WebRTCクライアントの再生先 = 仮想デバイスB、Meetのマイク = 仮想デバイスB の出力側 |
| アバター映像 → Meetのカメラ | WebRTCクライアント画面をOBSでウィンドウキャプチャ → OBS Virtual Camera をMeetのカメラに |

- WebRTCクライアントは別のChromeプロファイル(またはブラウザ)で開く。再生先の切替はChromeの `setSinkId` 対応が必要
- 自分の声のエコーを避けるため、Meet側のスピーカーは仮想デバイスAのみに出す(自分では聞こえなくなるのでモニターが要るなら集約デバイスを使う)
- 発表中は「AIであること」を明示する
