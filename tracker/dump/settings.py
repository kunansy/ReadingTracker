import os
from environs import Env


env = Env()
env.read_env()

with env.prefixed("DB_"):
    DB_HOST = '127.0.0.1'
    DB_PORT = 7432
    DB_USERNAME = env("USERNAME")
    DB_PASSWORD = env("PASSWORD")
    DB_NAME = env("NAME")

with env.prefixed("DRIVE_"):
    DRIVE_TOKEN_PATH = env.path("TOKEN_PATH", "tracker/dump/token.json")
    DRIVE_CREDS_PATH = env.path("CREDS_PATH", "tracker/dump/creds.json")

os.environ.clear()
