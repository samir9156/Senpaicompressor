# TG Video Compressor Bot

Video pe reply karo: `res 720 crf same codec h265`

## Setup
1. my.telegram.org se API_ID + API_HASH, @BotFather se BOT_TOKEN.
2. Railway project banao -> service -> Variables: API_ID, API_HASH, BOT_TOKEN.
3. Railway -> Project Settings -> Tokens -> project token banao.
4. GitHub repo -> Settings -> Secrets -> Actions:
   - RAILWAY_TOKEN = project token
   - RAILWAY_SERVICE = Railway service ka naam (ya ID)
5. `main` branch pe push karo -> auto deploy.
