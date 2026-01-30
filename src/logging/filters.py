"""
Logging filters for sensitive data redaction.

Automatically redacts:
- API keys and tokens
- Bearer tokens
- Private keys
- Sensitive user information
"""

import re
import hashlib
import logging
from typing import Any, Dict, List, Union


class SensitiveDataFilter(logging.Filter):
    """
    Filter that redacts sensitive data from log records.

    Protects against accidental logging of:
    - API keys (openai_api_key, openrouter_api_key, etc.)
    - Bearer tokens
    - Private keys (64-character hex strings)
    - Database URLs with passwords
    - Other sensitive patterns
    """

    # Regex patterns for sensitive data detection
    PATTERNS = {
        'api_key': r'(?i)(api[_-]?key|token|secret|password)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_-]{20,})["\']?',
        'bearer_token': r'Bearer\s+([a-zA-Z0-9_.-]+)',
        'private_key': r'\b([a-fA-F0-9]{64})\b',
        'database_url': r'(postgres|postgresql|mysql|mongodb)://([^:]+):([^@]+)@',
        'sk_key': r'\bsk-[a-zA-Z0-9]{20,}\b',  # OpenAI secret keys
        'xai_key': r'\bxai-[a-zA-Z0-9]{20,}\b',  # xAI/Grok keys
    }

    # Field names that should be redacted if they appear as dict keys
    SENSITIVE_KEYS = {
        'api_key',
        'apikey',
        'api-key',
        'token',
        'secret',
        'password',
        'private_key',
        'privatekey',
        'bearer',
        'authorization',
        'auth',
    }

    def __init__(self, redact_enabled: bool = True):
        """
        Initialize sensitive data filter.

        Args:
            redact_enabled: Whether to enable redaction (default: True)
        """
        super().__init__()
        self.redact_enabled = redact_enabled

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record by redacting sensitive data.

        Args:
            record: LogRecord to filter

        Returns:
            True (always pass the record through)
        """
        if not self.redact_enabled:
            return True

        # Redact message
        if isinstance(record.msg, str):
            record.msg = self._redact_text(record.msg)

        # Redact arguments
        if record.args:
            if isinstance(record.args, dict):
                record.args = self._redact_dict(record.args)
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(self._redact_value(arg) for arg in record.args)

        # Redact extra fields
        if hasattr(record, 'prompt') and isinstance(record.prompt, str):
            record.prompt = self._redact_text(record.prompt)

        if hasattr(record, 'response') and isinstance(record.response, dict):
            record.response = self._redact_dict(record.response)

        if hasattr(record, 'request') and isinstance(record.request, dict):
            record.request = self._redact_dict(record.request)

        if hasattr(record, 'context') and isinstance(record.context, dict):
            record.context = self._redact_dict(record.context)

        if hasattr(record, 'ai_metadata') and isinstance(record.ai_metadata, dict):
            record.ai_metadata = self._redact_dict(record.ai_metadata)

        return True

    def _redact_text(self, text: str) -> str:
        """
        Redact sensitive data from text using regex patterns.

        Args:
            text: Text to redact

        Returns:
            Redacted text
        """
        if not isinstance(text, str):
            return text

        redacted = text

        # Apply each pattern
        for pattern_name, regex in self.PATTERNS.items():
            if pattern_name == 'api_key':
                # Special handling for key-value pairs
                redacted = re.sub(
                    regex,
                    lambda m: f"{m.group(1)}=[REDACTED:API_KEY]",
                    redacted
                )
            elif pattern_name == 'bearer_token':
                redacted = re.sub(
                    regex,
                    'Bearer [REDACTED:BEARER_TOKEN]',
                    redacted
                )
            elif pattern_name == 'database_url':
                redacted = re.sub(
                    regex,
                    r'\1://[REDACTED:USER]:[REDACTED:PASSWORD]@',
                    redacted
                )
            else:
                redacted = re.sub(
                    regex,
                    f'[REDACTED:{pattern_name.upper()}]',
                    redacted
                )

        return redacted

    def _redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively redact sensitive data from dictionary.

        Args:
            data: Dictionary to redact

        Returns:
            Redacted dictionary
        """
        if not isinstance(data, dict):
            return data

        redacted = {}
        for key, value in data.items():
            # Check if key name is sensitive
            if key.lower() in self.SENSITIVE_KEYS:
                redacted[key] = '[REDACTED:SENSITIVE_KEY]'
            else:
                redacted[key] = self._redact_value(value)

        return redacted

    def _redact_value(self, value: Any) -> Any:
        """
        Redact sensitive data from any value type.

        Args:
            value: Value to redact

        Returns:
            Redacted value
        """
        if isinstance(value, str):
            return self._redact_text(value)
        elif isinstance(value, dict):
            return self._redact_dict(value)
        elif isinstance(value, (list, tuple)):
            return [self._redact_value(v) for v in value]
        else:
            return value

    @staticmethod
    def anonymize_user_id(user_id: Union[int, str]) -> str:
        """
        Anonymize user ID using hash.

        Args:
            user_id: User ID to anonymize

        Returns:
            Hashed user ID (first 16 characters)
        """
        user_id_str = str(user_id)
        hash_obj = hashlib.sha256(user_id_str.encode())
        return hash_obj.hexdigest()[:16]

    @staticmethod
    def anonymize_username(username: str) -> str:
        """
        Anonymize username using hash.

        Args:
            username: Username to anonymize

        Returns:
            Hashed username (first 12 characters)
        """
        if not username:
            return ""
        hash_obj = hashlib.sha256(username.encode())
        return f"user_{hash_obj.hexdigest()[:12]}"
