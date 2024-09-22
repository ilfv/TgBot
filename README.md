# Blitz Statistics BlitzHUB Project Page:
Support [![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?&logo=discord&logoColor=white)](https://discord.gg/24FAU6Gbv2)

This repo is Telegeam represent of [bot_project](https://github.com/SchottkyDi0de/bot_project)

# Used libriares:
pyyaml 6.0.1

aiohttp 3.10.5

aiogram 3.12.0

asynciolimiter 1.0.0

python-dotenv 1.0.0

pillow 10.0.1

cacheout 0.14.1

pydantic 2.4.2

the_retry 0.1.1

webcolors 1.13

dynamic-yaml 2.0.0

motor 3.4.0

numpy 2.0.0

pytz 2024.1


# Dependencies
[Python 3.11](https://www.python.org/downloads/release/python-3110/) or later

[datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator/) for `dev_tools/locale_gen.py`

[MongoDB Server](https://www.mongodb.com/try/download/community)

[MongoDB Database Tools](https://www.mongodb.com/try/download/database-tools) (for dumper)

[WOTB Replay parser tool](https://github.com/eigenein/wotbreplay-parser) (project include compiled version for win 10 - 11 and linux)

# Supported platform:
Any linux distribution capable of installing all dependencies (our server was on ubuntu 22.04 LTS)

Windows 8 or later
# Deployment
## 1: Install all dependencies

## 2: Create virtual enviroment for python libs
```bash
python3 -m venv .env
```
**and activate**
### windows:
```cmd
.env/scripts/activate
```
### Linux
```bash
source .env/bin/activate
```
## 3: install all required libs
```bash
pip install -r requirements.txt
```

## 4: Setup
Go to `lib/settings/` and create file `.env`

The `.env` file should have the following content (instead of <> text you should specify your data)

```env
DISCORD_TOKEN=<your main token>
DISCORD_TOKEN_DEV=<your test token>

WG_APP_ID_CL0=<Wargaming API Key 1>
WG_APP_ID_CL1=<Wargaming API Key 2>

LT_APP_ID_CL0=<Lesta API Key 1>
LT_APP_ID_CL1=<Lesta API Key 2>

TG_TOKEN=<Bot Token>
```
