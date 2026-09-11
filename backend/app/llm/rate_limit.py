"""LLM 速率限流 —— Token Bucket 令牌桶

三层防护体系中三层各自的职责：
- 背压（信号量，model_client._BackpressureMixin）：限制"同时"在途请求数 → 保护自己
- 限流（本模块 Token Bucket）：限制"发起"请求的速率 → 保护下游 API 配额（防 429）
- 熔断（redis_cache 三态机同款思路）：下游持续故障时快速失败 → 保护等待时间

令牌桶算法：容量 capacity 的桶以 rate 个/秒匀速补充令牌，每个请求取 1 个；
桶空时 sleep 等待补足（排队优先于报错，与背压哲学一致）。
与信号量的本质区别：信号量管"并发数"，令牌桶管"发起节奏"——
16 路流式各持续数分钟时，信号量早已饱和；新请求的"启动速率"由本桶约束。
"""
import asyncio
import time

from app.config import settings

_bucket: "AsyncTokenBucket | None" = None


class AsyncTokenBucket:
    """异步令牌桶。capacity = 1 秒的补充量（允许一秒内的合理突发）。"""
    # 突发容量就是“桶最多能攒多少令牌”，允许系统在空闲后短时间内突发处理多个请求，但长期平均速率仍由 rate 控制
    def __init__(self, rpm: int):
        self.rate = rpm / 60.0                              # 令牌/秒
        self.capacity = max(1, round(self.rate))            # 突发容量:桶的最大容量（上限）
        self.tokens = float(self.capacity)                  # 桶里当前有多少令牌
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()                         # 桶状态互斥

    async def acquire(self, tokens: int = 1) -> None:
        """取令牌；不足则计算缺口所需时长，锁外 sleep 后重试。"""
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.updated
                # 惰性补充：按流逝时间一次性补齐，而非定时器
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate) # 不能超过桶容量
                self.updated = now
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                need = (tokens - self.tokens) / self.rate
            # 锁外等待：不阻塞其他协程补充/取用令牌
            await asyncio.sleep(need)


def _get_bucket() -> "AsyncTokenBucket | None":
    """进程级单例（懒创建）。rpm<=0 表示禁用 → None。"""
    global _bucket
    if _bucket is None:
        rpm = settings.LLM_RATE_LIMIT_RPM
        if rpm > 0:
            _bucket = AsyncTokenBucket(rpm)
    return _bucket


async def acquire_rate_token() -> None:
    """取一个请求令牌；禁用时立即返回。主备 LLM 实例共享同一只桶。"""
    bucket = _get_bucket()
    if bucket is not None:
        await bucket.acquire()
