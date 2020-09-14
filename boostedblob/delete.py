import os
import shutil
from typing import AsyncIterator, Union

from .boost import BoostExecutor, EagerAsyncIterator, consume
from .listing import listtree
from .path import AzurePath, BasePath, CloudPath, GooglePath, LocalPath, isfile, pathdispatch
from .request import Request, azurify_request, googlify_request

# ==============================
# remove
# ==============================


@pathdispatch
async def remove(path: Union[BasePath, str]) -> None:
    """Delete the file ``path``.

    :param path: The path to delete.

    """
    raise ValueError(f"Unsupported path: {path}")


@remove.register  # type: ignore
async def _azure_remove(path: AzurePath) -> None:
    if path.is_directory_like():
        raise IsADirectoryError
    request = await azurify_request(
        Request(
            method="DELETE",
            url=path.format_url("https://{account}.blob.core.windows.net/{container}/{blob}"),
            success_codes=(202,),
            failure_exceptions={404: FileNotFoundError()},
        )
    )
    await request.execute_reponseless()


@remove.register  # type: ignore
async def _google_remove(path: GooglePath) -> None:
    if path.is_directory_like():
        raise IsADirectoryError
    request = await googlify_request(
        Request(
            method="DELETE",
            url=path.format_url("https://storage.googleapis.com/storage/v1/b/{bucket}/o/{blob}"),
            success_codes=(204,),
            failure_exceptions={404: FileNotFoundError()},
        )
    )
    await request.execute_reponseless()


@remove.register  # type: ignore
async def _local_remove(path: LocalPath) -> None:
    os.remove(path)


# ==============================
# rmtree
# ==============================


async def rmtree_iterator(path: CloudPath, executor: BoostExecutor) -> AsyncIterator[CloudPath]:
    """Delete the directory ``path``.

    Yields the deleted paths as they are deleted.

    :param path: The path to delete.
    :param executor: An executor.

    """
    dirpath = path.ensure_directory_like()
    subpath_exists = False

    async def remove_wrapper(entry: CloudPath) -> CloudPath:
        nonlocal subpath_exists
        subpath_exists = True
        await remove(entry)
        return entry

    it: EagerAsyncIterator[CloudPath] = EagerAsyncIterator(listtree(dirpath))  # type: ignore
    async for path in executor.map_unordered(remove_wrapper, it):
        yield path

    # If we find nothing, then run some checks so we throw the appropriate error.
    # Doing this means we avoid extra requests in the happy path.
    if not subpath_exists:
        if not await isfile(path):
            raise FileNotFoundError(path)
        raise NotADirectoryError(path)


@pathdispatch
async def rmtree(path: Union[BasePath, str], executor: BoostExecutor) -> None:
    """Delete the directory ``path``.

    :param path: The path to delete.
    :param executor: An executor.

    """
    raise ValueError(f"Unsupported path: {path}")


@rmtree.register  # type: ignore
async def _cloud_rmtree(path: CloudPath, executor: BoostExecutor) -> None:
    await consume(rmtree_iterator(path, executor))


@rmtree.register  # type: ignore
async def _local_rmtree(path: LocalPath, executor: BoostExecutor) -> None:
    shutil.rmtree(path)