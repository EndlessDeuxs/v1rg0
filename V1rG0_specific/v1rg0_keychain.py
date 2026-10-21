import os
import json
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class V1rg0Keychain:
    def __init__(self, master_password: str):
        self._keys: dict[str, str] = {}
        self._salt = b'V1rG0_Salt_2026'
        self._cipher = self._generate_cipher(master_password)
        self._load_keys()

    def _generate_cipher(self, password: str) -> Fernet:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=self._salt, iterations=100000)
        return Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode())))

    def _load_keys(self):
        key_file = "v1rg0_keys.enc"
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                encrypted_data = f.read()
            try:
                self._keys = json.loads(self._cipher.decrypt(encrypted_data))
            except Exception:
                self._keys = {}
        else:
            self._keys = {}
            self._save_keys()

    def _save_keys(self):
        with open("v1rg0_keys.enc", 'wb') as f:
            f.write(self._cipher.encrypt(json.dumps(self._keys).encode()))

    def add_key(self, key_id: str, key_value: str):
        self._keys[key_id] = key_value
        self._save_keys()

    # Hosted mode: API keys come from environment variables first,
    # then fall back to the encrypted local keychain file.
    ENV_KEY_MAP = {
        "deepseek_chat": "DEEPSEEK_API_KEY",
        "kimi_k2_6": "MOONSHOT_API_KEY",
    }

    def get_key(self, key_id: str) -> str | None:
        env_name = self.ENV_KEY_MAP.get(key_id)
        if env_name and os.environ.get(env_name):
            return os.environ[env_name]
        return self._keys.get(key_id, None)

    def list_keys(self) -> list[str]:
        return list(self._keys.keys())