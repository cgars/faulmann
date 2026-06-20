#!/usr/bin/env python3
"""
Import remote blog images referenced in Jekyll posts into this repository.

Usage:
  python scripts/import_remote_blog_images.py --dry-run
  python scripts/import_remote_blog_images.py
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".bmp",
    ".tif",
    ".tiff",
    ".avif",
    ".ico",
}

IMAGE_FIELD_PATTERN = re.compile(
    r'(?mi)^(?P<prefix>\s*(?:image|cover|thumbnail|og_image|hero|background)\s*:\s*)'
    r'(?P<quote>["\']?)(?P<url>https?://[^\s"\'#]+)(?P=quote)(?P<suffix>\s*(?:#.*)?)$'
)

MARKDOWN_IMAGE_PATTERN = re.compile(
    r'!\[[^\]]*]\(\s*(?:<)?(?P<url>https?://[^)\s>]+)(?:>)?'
)

HTML_IMAGE_PATTERN = re.compile(
    r'(<img\b[^>]*?\bsrc\s*=\s*)(?P<quote>["\']?)(?P<url>https?://[^"\'\s>]+)(?P=quote)',
    re.IGNORECASE,
)

LIQUID_IMAGE_PATTERN = re.compile(
    r'(\b(?:image|img|thumbnail|cover|hero|background|og_image)\s*=\s*)'
    r'(?P<quote>["\'])(?P<url>https?://[^"\']+)(?P=quote)',
    re.IGNORECASE,
)


@dataclass
class UrlImportResult:
    local_web_path: Optional[str]
    downloaded: bool
    warning: Optional[str] = None


class RemoteImageImporter:
    def __init__(self, repo_root: Path, dry_run: bool = False, timeout: int = 15) -> None:
        self.repo_root = repo_root
        self.posts_dir = repo_root / "_posts"
        self.assets_root = repo_root / "assets" / "img" / "posts"
        self.dry_run = dry_run
        self.timeout = timeout

        self.url_to_path: Dict[str, str] = {}
        self.failed_urls: Dict[str, str] = {}
        self.downloaded_urls: Set[str] = set()
        self.planned_urls: Set[str] = set()
        self._dir_state: Dict[str, Tuple[Set[str], int]] = {}

        self.posts_scanned = 0
        self.posts_changed = 0
        self.files_written = 0

    def run(self) -> int:
        if not self.posts_dir.exists():
            print(f"Error: posts directory does not exist: {self.posts_dir}", file=sys.stderr)
            return 1

        posts = sorted(
            p for p in self.posts_dir.iterdir() if p.is_file() and p.suffix.lower() in {".md", ".markdown"}
        )
        for post_path in posts:
            self.posts_scanned += 1
            self._process_post(post_path)

        self._print_summary()
        return 0

    def _process_post(self, post_path: Path) -> None:
        original_text = self._read_text_preserve_newlines(post_path)
        slug = post_path.stem

        front_matter, body = self._split_front_matter(original_text)

        updated_front_matter = self._replace_front_matter_urls(front_matter, slug, post_path)
        updated_body = self._replace_body_urls(body, slug, post_path)
        updated_text = updated_front_matter + updated_body

        if updated_text != original_text:
            self.posts_changed += 1
            if self.dry_run:
                print(f"DRY-RUN: would update {post_path}")
            else:
                self._write_text_preserve_newlines(post_path, updated_text)
                self.files_written += 1
                print(f"Updated {post_path}")

    def _replace_front_matter_urls(self, text: str, slug: str, post_path: Path) -> str:
        if not text:
            return text

        def replacer(match: re.Match[str]) -> str:
            remote_url = match.group("url")
            result = self._import_url(remote_url, slug, post_path)
            if not result.local_web_path:
                return match.group(0)
            return (
                f"{match.group('prefix')}{match.group('quote')}"
                f"{result.local_web_path}{match.group('quote')}{match.group('suffix')}"
            )

        return IMAGE_FIELD_PATTERN.sub(replacer, text)

    def _replace_body_urls(self, text: str, slug: str, post_path: Path) -> str:
        if not text:
            return text

        def replace_url_in_match(match: re.Match[str]) -> str:
            remote_url = match.group("url")
            result = self._import_url(remote_url, slug, post_path)
            if not result.local_web_path:
                return match.group(0)
            return match.group(0).replace(remote_url, result.local_web_path, 1)

        text = MARKDOWN_IMAGE_PATTERN.sub(replace_url_in_match, text)
        text = HTML_IMAGE_PATTERN.sub(replace_url_in_match, text)
        text = LIQUID_IMAGE_PATTERN.sub(replace_url_in_match, text)
        return text

    def _import_url(self, url: str, slug: str, post_path: Path) -> UrlImportResult:
        if not url.startswith(("http://", "https://")):
            return UrlImportResult(local_web_path=None, downloaded=False)

        if url in self.url_to_path:
            return UrlImportResult(local_web_path=self.url_to_path[url], downloaded=False)

        if url in self.failed_urls:
            return UrlImportResult(local_web_path=None, downloaded=False, warning=self.failed_urls[url])

        if self.dry_run:
            _, ext, final_name = self._build_filename_plan(url, slug, content_type=None)
            local_web_path = f"/assets/img/posts/{slug}/{final_name}"
            self.url_to_path[url] = local_web_path
            self.planned_urls.add(url)
            print(f"DRY-RUN: would download {url} -> {local_web_path} (ext={ext})")
            return UrlImportResult(local_web_path=local_web_path, downloaded=False)

        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "faulmann-remote-image-importer/1.0"},
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = response.read()
                content_type = response.headers.get("Content-Type", "")
                final_url = response.geturl() or url
        except Exception as exc:  # noqa: BLE001
            warning = f"failed download for {url} in {post_path.name}: {exc}"
            self.failed_urls[url] = warning
            print(f"WARNING: {warning}")
            return UrlImportResult(local_web_path=None, downloaded=False, warning=warning)

        if not data:
            warning = f"empty response for {url} in {post_path.name}"
            self.failed_urls[url] = warning
            print(f"WARNING: {warning}")
            return UrlImportResult(local_web_path=None, downloaded=False, warning=warning)

        base_name, ext, final_name = self._build_filename_plan(final_url, slug, content_type)
        is_image_by_ext = ext in IMAGE_EXTENSIONS
        normalized_content_type = content_type.split(";", 1)[0].strip().lower()
        is_image_by_type = normalized_content_type.startswith("image/")

        if not (is_image_by_ext or is_image_by_type):
            warning = (
                f"non-image response skipped for {url} in {post_path.name}: "
                f"content-type={normalized_content_type or 'unknown'}"
            )
            self.failed_urls[url] = warning
            print(f"WARNING: {warning}")
            return UrlImportResult(local_web_path=None, downloaded=False, warning=warning)

        target_dir = self.assets_root / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / final_name
        target_path.write_bytes(data)

        local_web_path = f"/assets/img/posts/{slug}/{final_name}"
        self.url_to_path[url] = local_web_path
        self.downloaded_urls.add(url)
        print(f"Downloaded {url} -> {local_web_path} ({base_name}{ext})")
        return UrlImportResult(local_web_path=local_web_path, downloaded=True)

    def _build_filename_plan(self, url: str, slug: str, content_type: Optional[str]) -> Tuple[str, str, str]:
        used_names, next_index = self._get_dir_state(slug)
        parsed = urllib.parse.urlparse(url)
        raw_name = os.path.basename(parsed.path)
        raw_name = urllib.parse.unquote(raw_name).strip()

        inferred_ext = self._infer_extension(raw_name, content_type)

        if raw_name:
            root, ext = os.path.splitext(raw_name)
            clean_root = self._sanitize_filename_root(root)
            chosen_ext = ext.lower() if ext.lower() in IMAGE_EXTENSIONS else inferred_ext
            candidate = f"{clean_root}{chosen_ext}"
        else:
            clean_root = "image"
            candidate = f"image-{next_index:02d}{inferred_ext}"
            next_index += 1

        candidate = self._ensure_unique_filename(candidate, used_names)
        used_names.add(candidate)
        self._dir_state[slug] = (used_names, next_index)

        final_root, final_ext = os.path.splitext(candidate)
        return final_root, final_ext.lower(), candidate

    def _get_dir_state(self, slug: str) -> Tuple[Set[str], int]:
        if slug in self._dir_state:
            return self._dir_state[slug]

        target_dir = self.assets_root / slug
        existing = {p.name for p in target_dir.glob("*")} if target_dir.exists() else set()
        state = (set(existing), 1)
        self._dir_state[slug] = state
        return state

    def _infer_extension(self, filename: str, content_type: Optional[str]) -> str:
        _, url_ext = os.path.splitext(filename)
        if url_ext.lower() in IMAGE_EXTENSIONS:
            return url_ext.lower()

        normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
        if normalized_content_type:
            guessed = mimetypes.guess_extension(normalized_content_type)
            if guessed == ".jpe":
                guessed = ".jpg"
            if guessed and guessed.lower() in IMAGE_EXTENSIONS:
                return guessed.lower()

        return ".jpg"

    @staticmethod
    def _sanitize_filename_root(root: str) -> str:
        root = re.sub(r"[^A-Za-z0-9._-]+", "-", root)
        root = root.strip("._-")
        return root or "image"

    @staticmethod
    def _ensure_unique_filename(candidate: str, used_names: Set[str]) -> str:
        if candidate not in used_names:
            return candidate
        root, ext = os.path.splitext(candidate)
        index = 2
        while True:
            alt = f"{root}-{index}{ext}"
            if alt not in used_names:
                return alt
            index += 1

    @staticmethod
    def _split_front_matter(text: str) -> Tuple[str, str]:
        if not text.startswith("---"):
            return "", text

        lines = text.splitlines(keepends=True)
        if not lines or lines[0].strip() != "---":
            return "", text

        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                front_matter = "".join(lines[: i + 1])
                body = "".join(lines[i + 1 :])
                return front_matter, body

        return "", text

    @staticmethod
    def _read_text_preserve_newlines(path: Path) -> str:
        with path.open("r", encoding="utf-8", newline="") as fh:
            return fh.read()

    @staticmethod
    def _write_text_preserve_newlines(path: Path, content: str) -> None:
        with path.open("w", encoding="utf-8", newline="") as fh:
            fh.write(content)

    def _print_summary(self) -> None:
        print("")
        print("Summary")
        print(f"- posts scanned: {self.posts_scanned}")
        print(f"- posts changed: {self.posts_changed}")
        if self.dry_run:
            print(f"- urls to download: {len(self.planned_urls)}")
        else:
            print(f"- images downloaded: {len(self.downloaded_urls)}")
            print(f"- files updated: {self.files_written}")
        print(f"- failed urls: {len(self.failed_urls)}")
        if self.failed_urls:
            print("Failed URL details:")
            for warning in self.failed_urls.values():
                print(f"  - {warning}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import remote blog images into local assets")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded and changed without writing files",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP request timeout in seconds (default: 15)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    importer = RemoteImageImporter(repo_root=repo_root, dry_run=args.dry_run, timeout=args.timeout)
    return importer.run()


if __name__ == "__main__":
    raise SystemExit(main())
