import random
import time
import re
from typing import List, Tuple, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp


# =========================
# Regex patterns
# =========================

# Markdown image: ![alt](url)
MD_IMG_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
# CQ image: [CQ:image,file=...]
CQ_IMG_RE = re.compile(r"\[CQ:image,[^\]]*?file=([^,\]]+)\]")
# Bare URL
URL_RE = re.compile(r"(https?://[^\s<>\]\)]+)")


@register("url_image_auto", "sin", "Auto convert image URLs to image segments", "0.1.1")
class UrlImageAuto(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # Default config fallback (in case schema is not loaded/migrated yet)
        self.cfg = self.context.config if hasattr(self.context, "config") else {}
        
    def _get_extensions(self) -> Tuple[str, ...]:
        exts = self.cfg.get("extensions", [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"])
        return tuple(exts)

    def _now_rand_seed(self) -> str:
        # time-based + random mix
        return str(int(time.time() * 1000) % 10_000_000 + random.randint(1, 9999))

    def _normalize_seed(self, url: str) -> str:
        """
        Replace seed=... with a random value if enabled.
        """
        if not self.cfg.get("randomize_seed", True):
            return url

        try:
            u = urlparse(url)
            qs = parse_qs(u.query, keep_blank_values=True)

            if "seed" in qs and qs["seed"]:
                seed_val = (qs["seed"][0] or "").strip()
                if seed_val.isdigit():
                    return url  # keep numeric seed
                
                # replace if it's "random value" keywords or non-digit
                if seed_val in ("随机值", "随机数字", "random", "rand") or (not seed_val.isdigit()):
                    qs["seed"] = [self._now_rand_seed()]
                    new_query = urlencode(qs, doseq=True)
                    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))

            return url
        except Exception:
            return url

    def _looks_like_image_url(self, url: str) -> Tuple[bool, str]:
        """
        Return (is_image, possibly_rewritten_url)
        """
        url2 = self._normalize_seed(url)
        try:
            p = urlparse(url2)
            host = (p.netloc or "").lower()
            path = (p.path or "").lower()

            # 1) Standard image extensions
            if path.endswith(self._get_extensions()):
                return True, url2

            # 2) Whitelisted rules
            rules = self.cfg.get("whitelist_rules", [])
            # If rules is just a default dict in some context quirks, handle it
            if not rules:
                # Default behavior if config missing
                 if host == "krcpsqplffnigtjeshns.supabase.co" and path.startswith("/functions/v1/random/biaoqing"):
                     return True, url2
            
            for rule in rules:
                if not isinstance(rule, dict): continue
                r_host = (rule.get("host") or "").lower()
                r_path = (rule.get("path_chars") or "").lower()
                
                if r_host and host == r_host:
                    if not r_path or path.startswith(r_path):
                        return True, url2

            return False, url2
        except Exception:
            return False, url2

    def _get_plain_text(self, comp) -> Optional[str]:
        if isinstance(comp, Comp.Plain):
            if hasattr(comp, "text"):
                return comp.text
            if hasattr(comp, "data"):
                d = comp.data
                if isinstance(d, str):
                    return d
                if isinstance(d, dict) and "text" in d:
                    return d.get("text", "")
            return ""
        return None

    def _make_plain(self, s: str) -> Comp.Plain:
        # Preserve layout with zero-width char
        return Comp.Plain(f"\u200b{s}\u200b")

    def _split_by_pattern(self, text: str, pattern: re.Pattern, force_image: bool) -> List[Tuple[str, str, bool]]:
        out: List[Tuple[str, str, bool]] = []
        idx = 0
        for m in pattern.finditer(text):
            if m.start() > idx:
                out.append(("plain", text[idx:m.start()], False))
            url = (m.group(1) or "").strip()
            out.append(("img", url, force_image))
            idx = m.end()
        if idx < len(text):
            out.append(("plain", text[idx:], False))
        return out

    def _convert_text_to_segments(self, text: str) -> List[Tuple[str, str]]:
        # Start with one plain block
        parts: List[Tuple[str, str, bool]] = [("plain", text, False)]

        # 1. Convert Markdown/CQ if enabled
        patterns = []
        if self.cfg.get("convert_cq_code", True):
            patterns.append(CQ_IMG_RE)
        if self.cfg.get("convert_markdown", True):
            patterns.append(MD_IMG_RE)

        for pat in patterns:
            new_parts: List[Tuple[str, str, bool]] = []
            for kind, payload, flag in parts:
                if kind != "plain":
                    new_parts.append((kind, payload, flag))
                    continue
                new_parts.extend(self._split_by_pattern(payload, pat, True))
            parts = new_parts

        # 2. Scan for bare URLs in remaining plain chunks
        final: List[Tuple[str, str]] = []
        for kind, payload, flag in parts:
            if kind == "img":
                # It was forced (MD or CQ), but still normalize seed
                new_url = self._normalize_seed(payload)
                final.append(("img", new_url))
                continue

            s = payload
            idx = 0
            # iterate URLs found in valid plain text
            for m in URL_RE.finditer(s):
                url = (m.group(1) or "").strip()
                ok, new_url = self._looks_like_image_url(url)
                if not ok:
                    continue

                # emit text before url
                if m.start() > idx:
                    final.append(("plain", s[idx:m.start()]))
                # emit image
                final.append(("img", new_url))
                idx = m.end()

            # remaining tail
            if idx < len(s):
                final.append(("plain", s[idx:]))

        return final

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        """
        Rewrite outgoing chain to replace text URLs with Image components.
        """
        result = event.get_result()
        if not result or not getattr(result, "chain", None):
            return

        new_chain = []
        changed = False

        for c in list(result.chain):
            text = self._get_plain_text(c)
            if text is None:
                # keep non-plain components as-is
                new_chain.append(c)
                continue

            segs = self._convert_text_to_segments(text)
            for kind, payload in segs:
                if kind == "plain":
                    if payload:
                        new_chain.append(self._make_plain(payload))
                else:
                    # image segment
                    new_chain.append(Comp.Image.fromURL(payload))
                    changed = True

        if changed:
            result.chain = new_chain

