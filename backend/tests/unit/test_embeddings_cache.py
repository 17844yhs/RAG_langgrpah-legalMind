"""L1 查询向量缓存单元测试

不加载真实模型：_QueryCacheMixin 通过 super().embed_query 的 MRO 语义，
与一个计数伪 embedder 组合即可验证缓存行为（同 query 只算一次、
归一化命中、LRU 淘汰、embed_documents 不缓存）。
"""
import pytest

from app.rag import embeddings as emb_mod
from app.rag.embeddings import _QueryCacheMixin


class _FakeBase:
    """伪真实 embedder：计数并返回可区分的向量"""

    def __init__(self):
        self.calls = 0

    def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        return [float(self.calls), 0.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[float(self.calls)] for _ in texts]


def _make_fake():
    """组合 mixin 与伪基类，模拟 CachedHuggingFaceEmbeddings 的继承结构"""
    class Fake(_QueryCacheMixin, _FakeBase):
        pass

    return Fake()


@pytest.fixture(autouse=True)
def _reset_cache():
    """逐测试清空全局 L1 缓存，避免用例间串扰"""
    emb_mod._query_cache.clear()


def test_same_query_embedded_once():
    fake = _make_fake()
    v1 = fake.embed_query("工伤赔偿怎么算")
    v2 = fake.embed_query("工伤赔偿怎么算")
    assert fake.calls == 1
    assert v1 == v2 == [1.0, 0.0]


def test_normalization_hits_same_key():
    """归一化与 Redis 键一致：大小写/空白折叠共享缓存"""
    fake = _make_fake()
    fake.embed_query("How to claim 工伤赔偿")
    fake.embed_query("how to claim  工伤赔偿 ")   # 大小写+多余空白
    assert fake.calls == 1


def test_different_query_recomputes():
    fake = _make_fake()
    fake.embed_query("工伤")
    fake.embed_query("离婚")
    assert fake.calls == 2


def test_lru_eviction(monkeypatch):
    """超过 maxsize 淘汰最久未用条目：淘汰后同 query 重新计算"""
    fake = _make_fake()
    monkeypatch.setattr(emb_mod, "_EMBED_CACHE_MAX", 2)
    fake.embed_query("q1")   # calls=1
    fake.embed_query("q2")   # calls=2
    fake.embed_query("q1")   # 命中 → 刷新到队尾，calls=2
    fake.embed_query("q3")   # 容量 2 → 淘汰队首 q2，calls=3
    fake.embed_query("q2")   # q2 已淘汰 → 重算 calls=4；插入又淘汰队首 q1
    assert fake.calls == 4
    fake.embed_query("q1")   # q1 刚被连坐淘汰 → 重算 calls=5
    assert fake.calls == 5
    fake.embed_query("q2")   # q2 仍在缓存 → 命中不重算
    assert fake.calls == 5


def test_hit_refreshes_lru_order(monkeypatch):
    """命中会刷新 LRU 顺序（move_to_end），这是淘汰语义的前提"""
    fake = _make_fake()
    monkeypatch.setattr(emb_mod, "_EMBED_CACHE_MAX", 2)
    fake.embed_query("a")
    fake.embed_query("b")
    fake.embed_query("a")    # a 刷新到队尾，b 变队首
    fake.embed_query("c")    # 淘汰 b
    fake.embed_query("b")    # b 重算
    assert fake.calls == 4


def test_embed_documents_not_cached():
    """索引构建批处理不走缓存，真实计算"""
    fake = _make_fake()
    fake.embed_documents(["a", "a"])
    assert fake.calls == 1


def test_repeat_hits_do_not_recompute():
    """连续命中同一键不重复计算（回归：dict.get 不改序，必须显式 move_to_end）"""
    fake = _make_fake()
    for _ in range(5):
        fake.embed_query("stable")
    assert fake.calls == 1
