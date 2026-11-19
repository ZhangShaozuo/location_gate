"""Download and read the published corpus formats."""

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
from tempfile import TemporaryDirectory
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile

try:
    import ijson
except ImportError:
    ijson = None


SPLITS = ("train", "dev", "test")
NAMES = ("massive", "cmpa", "crosswoz", "smp2019", "risawoz", "sgd")
TRAIN_ONLY_SOURCES = {"smp2019"}
CMPA = "417b15e5e988ac1a6241fb9b8aef60a35dbfe71c"
CROSS = "df82c9fdff91b9b130f2d6b89110d3870ba6260e"
SMP2019 = "65ad29bba6a625dea72b3353298171c43f927e4a"
SGD = "e852981ae34990f4358979625854259302feaa78"
HF_RISA = "https://huggingface.co/datasets/GEM/RiSAWOZ/resolve/main"
GITHUB = "https://raw.githubusercontent.com"
DOWNLOADS = {
    "massive": {"massive-1.1.tar.gz": (
        "https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz",
        "4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577",
    )},
    "cmpa": {"cmpa-full.zip": (
        f"{GITHUB}/XingChen-AGI/CMPA-SLU/{CMPA}/Full_Category.zip",
        "3e6fae4df25cb6edb678331ec785a0a81f968468447c4f85d86c9778bdbcd48f",
    )},
    "crosswoz": {
        f"crosswoz/{split}.json.zip": (
            f"{GITHUB}/thu-coai/CrossWOZ/{CROSS}/data/crosswoz/{split}.json.zip", None
        )
        for split in ("train", "val", "test")
    },
    "smp2019": {"smp2019/train.json": (
        f"{GITHUB}/ygwpz/SMP2019-ECDT-NLU/{SMP2019}/dataSet/train.json",
        "32e897dd76ab4dfa021f0334236514cf2f4d44e108e6e95984fd46d0a79e7a50",
    )},
    "risawoz": {
        f"risawoz/{split}.json": (f"{HF_RISA}/{split}.json", None)
        for split in SPLITS
    },
    "sgd": {"sgd.tar.gz": (
        f"https://codeload.github.com/google-research-datasets/dstc8-schema-guided-dialogue/tar.gz/{SGD}",
        None,
    )},
}


def sha256(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def download(url, dest, expected, timeout, retries):
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries + 1):
        try:
            with TemporaryDirectory(prefix=".corpus-download-", dir=dest.parent) as temporary:
                part = Path(temporary) / dest.name
                request = Request(url, headers={"User-Agent": "location-intent-corpora/1.0"})
                with urlopen(request, timeout=timeout) as response, part.open("wb") as target:
                    shutil.copyfileobj(response, target, length=1024 * 1024)
                    size = response.headers.get("Content-Length")
                if not part.stat().st_size or (size and part.stat().st_size != int(size)):
                    raise OSError(f"下载字节数不完整：{url}")
                if expected and sha256(part) != expected:
                    raise OSError(f"SHA-256 校验失败：{url}")
                part.replace(dest)
            return
        except (OSError, URLError, ValueError) as exc:
            permanent_http = isinstance(exc, HTTPError) and exc.code in {400, 401, 403, 404}
            if attempt == retries or permanent_http:
                raise OSError(f"无法下载 {url}：{exc}") from exc
            time.sleep(min(2 ** attempt, 8))


def local_sgd_files(root):
    return {
        split: sorted((root / "sgd" / split).glob("dialogues_*.json"))
        for split in SPLITS
    }


def ensure_source(root, dataset, offline=False, timeout=60, retries=2):
    local_massive = root / "zh-CN.jsonl"
    if dataset == "massive" and local_massive.is_file():
        return [{"path": str(local_massive), "sha256": sha256(local_massive), "url": None}]
    if dataset == "sgd" and (root / "sgd").is_dir():
        files = local_sgd_files(root)
        missing = [split for split, paths in files.items() if not paths]
        if missing:
            raise ValueError(f"已解压的 SGD 缺少划分：{', '.join(missing)}")
        return [
            {"path": str(path), "sha256": sha256(path), "url": None}
            for paths in files.values() for path in paths
        ]

    items = []
    for name, (url, expected) in DOWNLOADS[dataset].items():
        path = root / name
        if not path.is_file():
            if offline:
                raise FileNotFoundError(f"缺少 {path}，下载地址：{url}")
            download(url, path, expected, timeout, retries)
        digest = sha256(path)
        if expected and digest != expected:
            raise ValueError(f"{path} 与官方版本校验值不一致")
        items.append({"path": str(path), "sha256": digest, "url": url})
    return items


def read_json(stream, mode):
    if ijson:
        if mode == "mapping":
            yield from ijson.kvitems(stream, "", use_float=True)
        else:
            yield from ijson.items(stream, "item", use_float=True)
    else:
        doc = json.load(stream)
        yield from doc.items() if mode == "mapping" else doc


def zip_records(path, filename, mode):
    with ZipFile(path) as archive:
        matches = [
            item for item in archive.namelist()
            if not item.endswith("/") and PurePosixPath(item).name == filename
        ]
        if len(matches) != 1:
            raise ValueError(f"{path} 应包含唯一的 {filename}")
        with archive.open(matches[0]) as stream:
            yield from read_json(stream, mode)


def massive_records(root):
    path = root / "zh-CN.jsonl"
    if path.is_file():
        with path.open("rb") as stream:
            yield from map(json.loads, filter(bytes.strip, stream))
        return
    archive_path = root / "massive-1.1.tar.gz"
    with tarfile.open(archive_path, mode="r|gz") as archive:
        for member in archive:
            if member.isfile() and PurePosixPath(member.name).name == "zh-CN.jsonl":
                with io.BufferedReader(archive.extractfile(member)) as stream:
                    yield from map(json.loads, filter(bytes.strip, stream))
                return
    raise ValueError(f"{archive_path} 中没有 zh-CN.jsonl")


def sgd_records(root):
    if (root / "sgd").is_dir():
        for split, paths in local_sgd_files(root).items():
            for path in paths:
                with path.open("rb") as stream:
                    for row in read_json(stream, "array"):
                        yield split, row
        return
    path = root / "sgd.tar.gz"
    found = set()
    with tarfile.open(path, mode="r|gz") as archive:
        for member in archive:
            parts = PurePosixPath(member.name).parts
            if (
                not member.isfile() or len(parts) < 2 or parts[-2] not in SPLITS
                or not re.fullmatch(r"dialogues_\d+\.json", parts[-1])
            ):
                continue
            split = parts[-2]
            found.add(split)
            with io.BufferedReader(archive.extractfile(member)) as stream:
                for row in read_json(stream, "array"):
                    yield split, row
    if found != set(SPLITS):
        raise ValueError(f"{path} 缺少 SGD 划分：{', '.join(sorted(set(SPLITS) - found))}")


def source_records(root, dataset):
    """Iterate (original split, original group identifier, published object)."""
    if dataset == "massive":
        for row in massive_records(root):
            if row["locale"] != "zh-CN":
                raise ValueError(f"仅支持 MASSIVE zh-CN，收到 {row['locale']!r}")
            yield row["partition"], str(row["id"]), row
    elif dataset == "cmpa":
        for split, stem in zip(SPLITS, ("Train", "Val", "Test"), strict=True):
            filename = f"{stem}_Data_Full_Category.json"
            for number, row in enumerate(zip_records(root / "cmpa-full.zip", filename, "array")):
                yield split, f"{stem.lower()}:{number}", row
    elif dataset == "crosswoz":
        for split, native in zip(SPLITS, ("train", "val", "test"), strict=True):
            path = root / "crosswoz" / f"{native}.json.zip"
            for identifier, row in zip_records(path, f"{native}.json", "mapping"):
                yield split, str(identifier), row
    elif dataset == "smp2019":
        with (root / "smp2019" / "train.json").open("rb") as stream:
            for index, row in enumerate(read_json(stream, "array")):
                yield "train", str(index), row
    elif dataset == "risawoz":
        for split in SPLITS:
            with (root / "risawoz" / f"{split}.json").open("rb") as stream:
                for row in read_json(stream, "array"):
                    yield split, str(row["dialogue_id"]), row
    elif dataset == "sgd":
        for split, row in sgd_records(root):
            yield split, str(row["dialogue_id"]), row
