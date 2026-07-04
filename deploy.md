# Deploy To VPS

Server path:

```text
/home/codex/telegram-downloader-bot
```

From a local shell that has `scp`/`ssh` access:

```bash
cd /mnt/c/Users/MSI/Documents/Vibecoding/projects/telegram-downloader-bot

scp \
  bot.py mtproto_upload.py requirements.txt \
  start.sh stop.sh status.sh proxy-start.sh proxy-stop.sh logs.sh diagnose.sh \
  codex@95.181.213.67:/home/codex/telegram-downloader-bot/

ssh codex@95.181.213.67 '
  cd /home/codex/telegram-downloader-bot &&
  chmod +x *.sh &&
  .venv/bin/python -m pip install -r requirements.txt &&
  ./stop.sh &&
  ./start.sh &&
  ./status.sh
'
```

Then watch logs:

```bash
ssh codex@95.181.213.67 'cd /home/codex/telegram-downloader-bot && ./logs.sh'
```

Do not copy `.env` from local notes. Keep real tokens and API credentials only on the server.

