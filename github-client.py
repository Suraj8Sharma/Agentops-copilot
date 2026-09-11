import os
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv


load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

key = os.environ["ENCRYPTION_KEY"]  # match your actual .env var
f = Fernet(key.encode() if isinstance(key, str) else key)

ciphertext = "gAAAAABqmUHhmVRdF4591_-tY-RJ2RJLj4h8-KZURae9wkzcbU_BAaLE4VBF6k0d2T92ypA_CEhfRM5t7VbQuf0liB7rcqtIHSSQsgO5HauP2ZLTnRnDx-AXf-2hCPFc1OWgr2PGSd58"  # run locally only, don't send to me
token = f.decrypt(ciphertext.encode()).decode()
print(token)