"""Storage for the files PackDesk keeps under DATA_ROOT (invoice PDFs, fault attachments, ...).

These files are never served directly by the web server; views check who may open them.
The folder is read from the settings each time, so tests and other servers can point elsewhere,
and migrations refer to the `data_storage` callable instead of a path.
"""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class DataStorage(FileSystemStorage):
    @property
    def base_location(self):
        return str(settings.DATA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None  # no public URL: files go through views


def data_storage():
    return DataStorage()
