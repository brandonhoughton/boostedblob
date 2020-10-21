import asyncio

import pytest

import boostedblob as bbb

from . import helpers


@pytest.mark.asyncio
@bbb.ensure_session
async def test_sync(any_dir, other_any_dir):
    await asyncio.wait(
        [
            helpers.unsafe_create_file(any_dir / "f1"),
            helpers.unsafe_create_file(any_dir / "f2"),
            helpers.unsafe_create_file(any_dir / "f3"),
            helpers.unsafe_create_file(any_dir / "alpha" / "f4"),
            helpers.unsafe_create_file(any_dir / "alpha" / "f5"),
            helpers.unsafe_create_file(any_dir / "alpha" / "beta" / "f6"),
            helpers.unsafe_create_file(any_dir / "alpha" / "beta" / "f7"),
            helpers.unsafe_create_file(any_dir / "alpha" / "beta" / "gamma" / "f8"),
            helpers.unsafe_create_file(any_dir / "delta" / "f9", b"1234"),
            helpers.unsafe_create_file(any_dir / "delta" / "epsilon" / "f10"),
        ]
    )

    async def _listtree(d, base):
        return sorted([p.relative_to(base) async for p in bbb.listtree(d)])

    async with bbb.BoostExecutor(100) as e:
        # sleep since if we run sync too soon, we run into limits of mtime accuracy and end up
        # syncing more than what we need...
        await asyncio.sleep(1)
        await bbb.boost.consume(bbb.sync(any_dir, other_any_dir, e))
        assert await _listtree(any_dir, any_dir) == await _listtree(other_any_dir, other_any_dir)

        await asyncio.wait(
            [
                bbb.remove(any_dir / "f2"),
                # note the file size of f9 remains the same
                helpers.unsafe_create_file(any_dir / "delta" / "f9", b"ABCD"),
            ]
        )

        actions = sorted(
            await bbb.syncing.sync_iterator(any_dir, other_any_dir), key=lambda x: x.relpath
        )
        assert actions == [
            bbb.syncing.CopyAction("delta/f9", 4),
            bbb.syncing.DeleteAction("f2"),
        ]
        await bbb.boost.consume(bbb.sync(any_dir, other_any_dir, e, delete=True))
        assert await _listtree(any_dir, any_dir) == await _listtree(other_any_dir, other_any_dir)
