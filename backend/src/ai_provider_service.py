import os
import base64
import hashlib

import mysql.connector
import requests
from cryptography.fernet import Fernet, InvalidToken


# =========================
# DATABASE CONNECTION
# (own connection helper, same pattern as db_helper.py, to avoid a
# circular import with app.py)
# =========================
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
    )


SUPPORTED_PROVIDERS = {"gemini", "openai", "deepseek", "anthropic"}

PROVIDER_LABELS = {
    "gemini": "Gemini",
    "openai": "OpenAI / GPT",
    "deepseek": "DeepSeek",
    "anthropic": "Claude / Anthropic",
}


# =========================
# TABLE SETUP
# =========================
def ensure_ai_provider_configs_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_provider_configs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            provider VARCHAR(50) NOT NULL,
            model_name VARCHAR(100) NOT NULL,
            encrypted_api_key TEXT NOT NULL,
            key_hint VARCHAR(20) NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            test_status VARCHAR(50) NOT NULL DEFAULT 'not_tested',
            last_tested_at DATETIME NULL,
            created_by INT NULL,
            updated_by INT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_ai_provider_configs_active (is_active)
        )
    """)


# =========================
# ENCRYPTION
#
# API keys are encrypted at rest with Fernet (AES-128-CBC + HMAC).
# AI_KEY_ENCRYPTION_SECRET can be any string -- it's hashed into a proper
# 32-byte key so you don't have to generate a base64 Fernet key by hand.
# =========================
def _get_fernet():
    secret = os.getenv("AI_KEY_ENCRYPTION_SECRET", "")

    if not secret:
        raise RuntimeError(
            "AI_KEY_ENCRYPTION_SECRET is not configured on the backend."
        )

    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(digest)

    return Fernet(fernet_key)


def encrypt_api_key(raw_key):
    return _get_fernet().encrypt(raw_key.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted_key):
    try:
        return _get_fernet().decrypt(encrypted_key.encode("utf-8")).decode("utf-8")
    except InvalidToken as error:
        raise RuntimeError("Stored AI provider key could not be decrypted.") from error


def mask_api_key(raw_key):
    raw_key = str(raw_key or "")

    if len(raw_key) <= 4:
        return "*" * len(raw_key)

    return ("*" * (len(raw_key) - 4)) + raw_key[-4:]


# =========================
# CONFIG READ / WRITE
# =========================
def get_active_ai_provider_config(cursor):
    cursor.execute("""
        SELECT *
        FROM ai_provider_configs
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
    """)

    return cursor.fetchone()


def get_ai_provider_public_config(cursor):
    """Same as get_active_ai_provider_config, but strips the encrypted key
    entirely -- this is the shape returned to the frontend."""
    config = get_active_ai_provider_config(cursor)

    if not config:
        return None

    return {
        "provider": config.get("provider"),
        "providerLabel": PROVIDER_LABELS.get(config.get("provider"), config.get("provider")),
        "modelName": config.get("model_name"),
        "keyHint": config.get("key_hint"),
        "testStatus": config.get("test_status"),
        "lastTestedAt": (
            config["last_tested_at"].strftime("%d/%m/%Y %I:%M %p")
            if config.get("last_tested_at")
            else None
        ),
    }


def save_ai_provider_config(cursor, provider, model_name, raw_api_key, actor_id):
    # Only one config is ever "active" at a time -- deactivate any previous
    # one instead of deleting it, so there's a history trail.
    cursor.execute("UPDATE ai_provider_configs SET is_active = 0 WHERE is_active = 1")

    encrypted_key = encrypt_api_key(raw_api_key)
    key_hint = mask_api_key(raw_api_key)

    cursor.execute("""
        INSERT INTO ai_provider_configs
        (provider, model_name, encrypted_api_key, key_hint, is_active, test_status, created_by, updated_by)
        VALUES (%s, %s, %s, %s, 1, 'not_tested', %s, %s)
    """, (provider, model_name, encrypted_key, key_hint, actor_id, actor_id))

    return cursor.lastrowid


def update_active_provider_test_status(cursor, success):
    cursor.execute("""
        UPDATE ai_provider_configs
        SET test_status = %s,
            last_tested_at = NOW()
        WHERE is_active = 1
    """, ("connected" if success else "failed",))


# =========================
# PROVIDER CALLS
#
# Every provider is called with a plain (prompt -> text) contract so any
# feature (quiz generation, chat, future tools) can use generate_ai_reply()
# without caring which provider is actually configured.
# =========================
def _call_gemini(prompt, model_name, api_key, timeout):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"

    response = requests.post(
        url,
        params={"key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_openai_compatible(prompt, model_name, api_key, timeout, base_url):
    response = requests.post(
        base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    return data["choices"][0]["message"]["content"]


def _call_anthropic(prompt, model_name, api_key, timeout):
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model_name,
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    return data["content"][0]["text"]


def call_ai_provider(prompt, provider, model_name, api_key, timeout=20):
    provider = str(provider or "").strip().lower()

    if provider == "gemini":
        return _call_gemini(prompt, model_name, api_key, timeout)

    if provider == "openai":
        return _call_openai_compatible(
            prompt, model_name, api_key, timeout,
            base_url="https://api.openai.com/v1/chat/completions",
        )

    if provider == "deepseek":
        return _call_openai_compatible(
            prompt, model_name, api_key, timeout,
            base_url="https://api.deepseek.com/chat/completions",
        )

    if provider == "anthropic":
        return _call_anthropic(prompt, model_name, api_key, timeout)

    raise ValueError(f"Unsupported AI provider: {provider}")


class AIProviderNotConfiguredError(Exception):
    pass


def generate_ai_reply(prompt, timeout=30):
    """
    High-level helper for any feature (AI Chat, AI Generated Quiz, future
    tools) that just wants text back from whichever provider the manager
    has configured, without knowing which provider that is.
    """
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        ensure_ai_provider_configs_table(cursor)
        config = get_active_ai_provider_config(cursor)

        if not config:
            raise AIProviderNotConfiguredError(
                "AI model is not configured yet. Please ask a manager to set it up in AI Model Settings."
            )

        api_key = decrypt_api_key(config["encrypted_api_key"])

        return call_ai_provider(
            prompt,
            config["provider"],
            config["model_name"],
            api_key,
            timeout=timeout,
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
