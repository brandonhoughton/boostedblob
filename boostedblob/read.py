from __future__ import annotations

import itertools
from typing import Any, Iterator, Optional, Tuple, Union

from .boost import BoostExecutor, BoostUnderlying, OrderedBoostable, UnorderedBoostable
from .globals import config
from .path import AzurePath, BasePath, CloudPath, GooglePath, LocalPath, getsize, pathdispatch
from .request import Request, azurify_request, googlify_request

ByteRange = Tuple[int, int]

# ==============================
# read_byte_range
# ==============================


@pathdispatch
async def read_byte_range(path: Union[CloudPath, str], byte_range: ByteRange) -> bytes:
    """Read the content of ``path`` in the given byte range.

    :param path: The path to read from.
    :param byte_range: The byte range to read.
    :return: The relevant bytes.

    """
    raise ValueError(f"Unsupported path: {path}")


@read_byte_range.register  # type: ignore
async def _azure_read_byte_range(path: AzurePath, byte_range: ByteRange) -> bytes:
    request = await azurify_request(
        Request(
            method="GET",
            url=path.format_url("https://{account}.blob.core.windows.net/{container}/{blob}"),
            headers={"Range": _byte_range_to_str(byte_range)},
            success_codes=(206,),
        )
    )
    async with request.execute() as resp:
        return await resp.read()


@read_byte_range.register  # type: ignore
async def _google_read_byte_range(path: GooglePath, byte_range: ByteRange) -> bytes:
    request = await googlify_request(
        Request(
            method="GET",
            url=path.format_url("https://storage.googleapis.com/storage/v1/b/{bucket}/o/{blob}"),
            params=dict(alt="media"),
            headers={"Range": _byte_range_to_str(byte_range)},
            success_codes=(206,),
        )
    )
    async with request.execute() as resp:
        return await resp.read()


# ==============================
# read_stream
# ==============================


@pathdispatch
async def read_stream(
    path: Union[BasePath, str], executor: BoostExecutor, size: Optional[int] = None
) -> BoostUnderlying[bytes]:
    """Read the content of ``path``.

    :param path: The path to read from.
    :param executor: An executor.
    :param size: If specified, will save a network call.
    :return: The stream of bytes, chunking determined by ``config.chunk_size``.

    """
    raise ValueError(f"Unsupported path: {path}")


@read_stream.register  # type: ignore
async def _cloud_read_stream(
    path: CloudPath, executor: BoostExecutor, size: Optional[int] = None
) -> OrderedBoostable[Any, bytes]:
    if size is None:
        size = await getsize(path)

    byte_ranges = itertools.zip_longest(
        range(0, size, config.chunk_size),
        range(config.chunk_size, size, config.chunk_size),
        fillvalue=size,
    )

    # Note that we purposefully don't do
    # https://docs.aiohttp.org/en/stable/client_quickstart.html#streaming-response-content
    # Doing that would stream data as we needed it, which is a little too lazy for our purposes
    chunks = executor.map_ordered(lambda byte_range: read_byte_range(path, byte_range), byte_ranges)
    return chunks


@read_stream.register  # type: ignore
async def _local_read_stream(
    path: LocalPath, executor: BoostExecutor, size: Optional[int] = None
) -> Iterator[bytes]:
    def iterator() -> Iterator[bytes]:
        with open(path, "rb") as f:
            while True:
                data = f.read(config.chunk_size)
                if not data:
                    return
                yield data

    return iterator()


# ==============================
# read_stream_unordered
# ==============================


@pathdispatch
async def read_stream_unordered(
    path: Union[CloudPath, str], executor: BoostExecutor, size: Optional[int] = None
) -> UnorderedBoostable[Any, Tuple[bytes, ByteRange]]:
    assert isinstance(path, CloudPath)

    if size is None:
        size = await getsize(path)

    byte_ranges = itertools.zip_longest(
        range(0, size, config.chunk_size),
        range(config.chunk_size, size, config.chunk_size),
        fillvalue=size,
    )

    async def read_byte_range_wrapper(byte_range: ByteRange) -> Tuple[bytes, ByteRange]:
        chunk = await read_byte_range(path, byte_range)
        return (chunk, byte_range)

    chunks = executor.map_unordered(read_byte_range_wrapper, byte_ranges)
    return chunks


# ==============================
# helpers
# ==============================


def _byte_range_to_str(byte_range: Tuple[Optional[int], Optional[int]]) -> str:
    # https://docs.microsoft.com/en-us/rest/api/storageservices/specifying-the-range-header-for-blob-service-operations
    # https://cloud.google.com/storage/docs/xml-api/get-object-download
    # oddly range requests are not mentioned in JSON API, only in the XML API
    start, end = byte_range
    if start is not None and end is not None:
        return f"bytes={start}-{end-1}"
    if start is not None:
        return f"bytes={start}-"
    if end is not None:
        if end > 0:
            return f"bytes=0-{end-1}"
        # This form is not supported by Azure
        return f"bytes=-{-int(end)}"
    raise AssertionError
