"""Prompt Injection Defense, Sanitization, and Instruction Boundary Shielding."""

import re
from typing import Any, Dict, List
from security_hardening.core.config import security_settings
from security_hardening.core.errors import PromptInjectionDetectedError


class PromptInjectionGuard:
    """Detects adversarial jailbreaks and prompt injection attempts in agent requirements and descriptions."""

    INJECTION_PATTERNS = [
        re.compile(r"(ignore|disregard|forget|override)\s+(all\s+)?((previous|prior|above|existing)\s+)?(instructions|prompts|rules|policies|budget)", re.IGNORECASE),
        re.compile(r"system\s+(override|prompt|directive)", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+(in\s+developer\s+mode|dan|unfiltered|jailbroken)", re.IGNORECASE),
        re.compile(r"always\s+(approve|authorize|allow)\s+this", re.IGNORECASE),
        re.compile(r"bypass\s+(policy|budget|approval|authorization|control\s+plane).*", re.IGNORECASE),
        re.compile(r"output\s+only\s+the\s+following\s+json", re.IGNORECASE),
        re.compile(r"admin_override\s*=\s*true", re.IGNORECASE),
        re.compile(r"<\s*script\s*>", re.IGNORECASE),
        re.compile(r"```(python|bash|sh|cmd).*rm\s+-rf", re.IGNORECASE),
    ]

    @classmethod
    def scan_text(cls, text: str) -> None:
        """Scan free-text field for known prompt-injection and instruction-override sequences."""
        if not security_settings.PROMPT_INJECTION_SCAN_ENABLED or not text:
            return

        for pattern in cls.INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                raise PromptInjectionDetectedError(match.group(0))

    @classmethod
    def sanitize_procurement_inputs(
        cls,
        item_description: str,
        category: str,
        requirements: Dict[str, Any],
    ) -> None:
        """Recursively scan all purchase input vectors before passing to ML ranker."""
        cls.scan_text(item_description)
        cls.scan_text(category)

        def scan_dict(d: Dict[str, Any]):
            for k, v in d.items():
                if isinstance(v, str):
                    cls.scan_text(v)
                elif isinstance(v, dict):
                    scan_dict(v)
                elif isinstance(v, list):
                    for elem in v:
                        if isinstance(elem, str):
                            cls.scan_text(elem)

        scan_dict(requirements)

