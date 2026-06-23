"""
storage.py  --  Google Cloud Storage manager
==============================================
Class-based wrapper around google-cloud-storage. Reads the bucket name
from the GCS_STAGING_BUCKET environment variable and uses Application
Default Credentials (ADC) for authentication.

Usage:
    from storage import StorageManager

    gcs = StorageManager()
    uri = gcs.upload_file("local/image.png", "scenes/scene_00.png")
    path = gcs.download_file("scenes/scene_00.png", "downloads/")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from stickman_studio.config import settings

log = logging.getLogger("stickman_studio.storage")


class StorageManager:
    """Manages GCS operations for a single bucket.

    The bucket is resolved from the GCS_STAGING_BUCKET env var at
    construction time. All methods raise ValueError if it is empty.

    Authentication is handled automatically via Application Default
    Credentials (GOOGLE_APPLICATION_CREDENTIALS or gcloud ADC).
    """

    def __init__(self, bucket_name: Optional[str] = None) -> None:
        """Initialize with an optional explicit bucket name.

        Args:
            bucket_name: GCS bucket name. If None, reads from the
                         GCS_STAGING_BUCKET environment variable.

        Raises:
            ValueError: If no bucket name is configured.
        """
        self._bucket_name = bucket_name or settings.gcs_staging_bucket
        if not self._bucket_name:
            raise ValueError(
                "No GCS bucket configured. Set GCS_STAGING_BUCKET in .env "
                "or pass bucket_name to StorageManager()."
            )
        self._client: "google.cloud.storage.Client | None" = None
        log.info("StorageManager initialised for bucket: %s", self._bucket_name)

    # ------------------------------------------------------------------ #
    # Lazy client
    # ------------------------------------------------------------------ #

    @property
    def client(self):
        """Lazy-initialised google-cloud-storage Client."""
        if self._client is None:
            from google.cloud import storage as gcs
            self._client = gcs.Client(project=settings.gcp_project_id)
        return self._client

    @property
    def bucket(self):
        """The bucket object bound to this instance."""
        return self.client.bucket(self._bucket_name)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def upload_file(
        self,
        local_path: str | Path,
        destination_blob_name: str,
    ) -> str:
        """Upload a local file to GCS.

        Args:
            local_path: Path to the local file to upload.
            destination_blob_name: Remote blob name (e.g.
                                   "projects/my_topic/images/scene_00.png").

        Returns:
            The gs:// URI of the uploaded blob.

        Raises:
            FileNotFoundError: If the local file does not exist.
        """
        source = Path(local_path)
        if not source.is_file():
            raise FileNotFoundError(f"Source file not found: {source}")

        blob = self.bucket.blob(destination_blob_name)
        blob.upload_from_filename(str(source))

        uri = f"gs://{self._bucket_name}/{destination_blob_name}"
        log.info("Uploaded %s -> %s", source.name, uri)
        return uri

    def download_file(
        self,
        blob_name: str,
        local_destination: str | Path,
    ) -> Path:
        """Download a GCS blob to a local file.

        Args:
            blob_name: Remote blob name to download.
            local_destination: Local path (file or directory) to write to.

        Returns:
            The local path the file was written to.

        Raises:
            google.cloud.exceptions.NotFound: If the blob does not exist.
        """
        dest = Path(local_destination)
        if dest.suffix:
            dest.parent.mkdir(parents=True, exist_ok=True)
        else:
            dest.mkdir(parents=True, exist_ok=True)
            dest = dest / Path(blob_name).name

        blob = self.bucket.blob(blob_name)
        blob.download_to_filename(str(dest))

        log.info("Downloaded gs://%s/%s -> %s", self._bucket_name, blob_name, dest)
        return dest

    def list_blobs(self, prefix: str = "") -> list[str]:
        """List blob names under the given prefix."""
        blobs = self.client.list_blobs(self._bucket_name, prefix=prefix)
        names = [b.name for b in blobs]
        log.info("Listed %d blobs under gs://%s/%s", len(names), self._bucket_name, prefix)
        return names

    def delete_blob(self, blob_name: str) -> bool:
        """Delete a single blob. Returns True if successful."""
        blob = self.bucket.blob(blob_name)
        blob.delete()
        log.info("Deleted gs://%s/%s", self._bucket_name, blob_name)
        return True

    def blob_exists(self, blob_name: str) -> bool:
        """Check whether a blob exists remotely."""
        return self.bucket.blob(blob_name).exists()

    def upload_directory(
        self,
        local_dir: str | Path,
        prefix: str = "",
    ) -> int:
        """Upload every file under local_dir to GCS under *prefix*.

        Returns the number of files uploaded.
        """
        root = Path(local_dir)
        if not root.is_dir():
            raise NotADirectoryError(f"Not a directory: {root}")

        count = 0
        for fpath in root.rglob("*"):
            if not fpath.is_file():
                continue
            blob_name = f"{prefix}/{fpath.relative_to(root)}".replace("\\", "/")
            self.bucket.blob(blob_name).upload_from_filename(str(fpath))
            count += 1

        log.info("Uploaded %d files from %s to gs://%s/%s",
                 count, root, self._bucket_name, prefix)
        return count
