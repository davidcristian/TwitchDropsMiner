from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import json
import logging
from functools import partial
from typing import Dict, TypedDict, NewType, TYPE_CHECKING

from translate import _
from exceptions import ExitRequest, ReloadRequest
from savefiles import save_each
from utils import json_load, json_save
from imagedata import decode_image, png_mode
from constants import URLType, CACHE_PATH, CACHE_DB

from PIL import Image as Image_module
from PIL.ImageTk import PhotoImage


if TYPE_CHECKING:
    from gui import GUIManager
    from PIL.Image import Image
    from typing_extensions import TypeAlias


logger = logging.getLogger("TwitchDrops")
ImageHash = NewType("ImageHash", str)
ImageSize: TypeAlias = "tuple[int, int]"


class ExpiringHash(TypedDict):
    hash: ImageHash
    expires: datetime


Hashes = Dict[URLType, ExpiringHash]
default_database: Hashes = {}
# A file of this name and size is the white image that cache/ can still map a failed download to; get() downloads
# such a URL again. The size tells it apart from a downloaded image of one color, which has the same name.
OLD_FAILED_DOWNLOAD = (ImageHash("fffffffffffffffffffffffff.png"), (10, 10))


class ImageCache:
    LIFETIME = timedelta(days=7)

    def __init__(self, manager: GUIManager) -> None:
        self._root = manager._root
        self._twitch = manager._twitch
        cleanup: bool = False
        CACHE_PATH.mkdir(parents=True, exist_ok=True)
        try:
            self._hashes: Hashes = json_load(CACHE_DB, default_database, merge=False)
        except json.JSONDecodeError:
            # if we can't load the mapping file, delete all existing files,
            # then reinitialize the image cache anew
            cleanup = True
            self._hashes = default_database.copy()
        self._images: dict[ImageHash, Image] = {}
        self._photos: dict[tuple[ImageHash, ImageSize], PhotoImage] = {}
        self._blanks: dict[ImageSize, PhotoImage] = {}
        self._failed: set[URLType] = set()
        self._lock = asyncio.Lock()
        self._altered: bool = False
        # cleanup the URLs
        hash_counts: dict[ImageHash, int] = {}
        now = datetime.now(timezone.utc)
        for url, hash_dict in list(self._hashes.items()):
            img_hash = hash_dict["hash"]
            if img_hash not in hash_counts:
                hash_counts[img_hash] = 0
            if now >= hash_dict["expires"]:
                del self._hashes[url]
                self._altered = True
            else:
                hash_counts[img_hash] += 1
        for img_hash, count in hash_counts.items():
            if count == 0:
                # hashes come with an extension already
                CACHE_PATH.joinpath(img_hash).unlink(missing_ok=True)
                # NOTE: The hashes are deleted from self._hashes above
        if cleanup:
            # This cleanups the cache folder from unused PNG files
            orphans = [
                file.name for file in CACHE_PATH.glob("*.png") if file.name not in hash_counts
            ]
            for filename in orphans:
                CACHE_PATH.joinpath(filename).unlink(missing_ok=True)

    def save(self, *, force: bool = False) -> None:
        if self._altered or force:
            json_save(CACHE_DB, self._hashes, sort=True)

    def retry_failed(self) -> None:
        """Have the next get() of each URL whose download failed download it again."""
        self._failed.clear()

    def _new_expires(self) -> datetime:
        return datetime.now(timezone.utc) + self.LIFETIME

    def _hash(self, image: Image) -> ImageHash:
        pixel_data = list(
            image.resize((10, 10), Image_module.Resampling.LANCZOS).convert('L').tobytes()
        )
        avg_pixel = sum(pixel_data) / len(pixel_data)
        bits = ''.join('1' if px >= avg_pixel else '0' for px in pixel_data)
        return ImageHash(f"{int(bits, 2):x}.png")

    async def get(self, url: URLType, size: ImageSize | None = None) -> PhotoImage:
        async with self._lock:
            image: Image | None = None
            if url in self._hashes:
                img_hash = self._hashes[url]["hash"]
                self._hashes[url]["expires"] = self._new_expires()
                if img_hash in self._images:
                    image = self._images[img_hash]
                else:
                    try:
                        loaded = Image_module.open(CACHE_PATH / img_hash)
                        loaded.load()  # force full decode so broken data is caught here
                        if (img_hash, loaded.size) != OLD_FAILED_DOWNLOAD:
                            self._images[img_hash] = image = loaded
                    except (FileNotFoundError, Image_module.UnidentifiedImageError, OSError):
                        pass
            if image is None and url not in self._failed:
                image = await self._download(url)
                if image is None:
                    # not mapped, so that the first get() after the next reload downloads it again
                    self._failed.add(url)
                else:
                    image = image.convert(png_mode(image.mode))
                    img_hash = self._hash(image)
                    self._images[img_hash] = image
                    # the URL is mapped even when the save fails: this run keeps the image in memory,
                    # and the next run cannot load the file and downloads the image again
                    save_each(
                        [partial(image.save, CACHE_PATH / img_hash)],
                        lambda error: logger.error(
                            _("error", "file_not_saved").format(file=f"{CACHE_PATH.name}/{img_hash}", error=error)
                        ),
                    )
                    self._hashes[url] = {
                        "hash": img_hash,
                        "expires": self._new_expires()
                    }
        self._altered = True
        if image is None:
            return self._blank(size or (10, 10))
        if size is None:
            size = image.size
        photo_key = (img_hash, size)
        if photo_key in self._photos:
            return self._photos[photo_key]
        if image.size != size:
            try:
                image = image.resize(size, Image_module.Resampling.LANCZOS)
            except OSError:
                # broken image data surfaced during resize; fall back to blank placeholder
                image = Image_module.new("RGB", size, (255, 255, 255))
        self._photos[photo_key] = photo = PhotoImage(master=self._root, image=image)
        return photo

    async def _download(self, url: URLType) -> Image | None:
        """Return the image at url, or None after a warning when the download gives no whole image."""
        try:
            async with self._twitch.request("GET", url) as response:
                image: Image | None = None
                if response.status != 404:
                    image = decode_image(await response.read(), Image_module.open)
                if image is None:
                    logger.warning(f"Image download gave no whole image (status {response.status}): {url}")
                return image
        except (ExitRequest, ReloadRequest):
            raise
        except Exception as exc:
            # not repr(exc): the repr of a connection error shows the proxy password
            logger.warning(f"Image download failed ({type(exc).__name__}: {exc}): {url}")
            return None

    def _blank(self, size: ImageSize) -> PhotoImage:
        """Return a white image of the given size, which stands in for an image whose download failed."""
        if size not in self._blanks:
            blank = Image_module.new("RGB", size, (255, 255, 255))
            self._blanks[size] = PhotoImage(master=self._root, image=blank)
        return self._blanks[size]
