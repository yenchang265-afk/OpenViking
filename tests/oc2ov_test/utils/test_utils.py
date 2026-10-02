"""
測試工具模組
提供 Session ID 管理、智慧等待、重試機制、測試資料管理等功能
"""

import functools
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 固定的 Session ID，用於 CI 環境避免 session 爆滿
# 使用 UUID 格式，確保 OpenClaw 直接使用，不做 SHA256 轉換
FIXED_SESSION_ID = "00000000-0000-0000-0000-000000000001"

# CI 環境下基於名稱生成確定性 UUID 的名稱空間
_CI_SESSION_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _ci_deterministic_uuid(name: str) -> str:
    """基於名稱生成確定性 UUID，CI 環境下同一名稱始終返回同一 UUID。"""
    return str(uuid.uuid5(_CI_SESSION_NAMESPACE, name))


def _is_ci_environment() -> bool:
    """檢測是否在 CI 環境中執行"""
    return bool(
        os.environ.get("CI")
        or os.environ.get("GITHUB_ACTIONS")
        or os.environ.get("GITLAB_CI")
        or os.environ.get("TRAVIS")
        or os.environ.get("CIRCLECI")
        or os.environ.get("JENKINS_URL")
    )


class SessionIdManager:
    """
    Session ID 管理器
    自動生成唯一的 session_id，支援字首和字尾
    在 CI 環境中使用固定的 session ID，避免 session 爆滿
    """

    _instance = None
    _session_registry: Dict[str, Dict[str, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def generate_session_id(
        prefix: str = "test",
        include_timestamp: bool = True,
        include_uuid: bool = True,
    ) -> str:
        """
        生成唯一的 session_id (UUID 格式)

        OpenClaw 會將非 UUID 格式的 session ID 轉換為 SHA256 雜湊，
        使用 UUID 格式可以確保 OpenClaw 直接使用，不做轉換。

        Args:
            prefix: session_id 字首 (僅用於日誌，不影響 UUID 格式)
            include_timestamp: 是否包含時間戳 (已忽略，保持介面相容)
            include_uuid: 是否包含 UUID (已忽略，始終使用 UUID)

        Returns:
            str: UUID 格式的 session_id
        """
        # 在 CI 環境中使用基於字首的確定性 session ID，避免不同測試互相干擾
        if _is_ci_environment():
            session_id = _ci_deterministic_uuid(f"session:{prefix}")
            logger.info(f"CI 環境檢測到，使用確定性 Session ID: {session_id} (prefix: {prefix})")
            return session_id

        # 生成 UUID 格式的 session ID
        session_id = str(uuid.uuid4())
        logger.info(f"生成 Session ID: {session_id} (prefix: {prefix})")
        return session_id

    @staticmethod
    def generate_test_class_session_id(test_class_name: str) -> str:
        """
        為測試類生成 session_id

        Args:
            test_class_name: 測試類名稱

        Returns:
            str: 唯一的 session_id
        """
        # 在 CI 環境中使用基於類名的確定性 session ID，避免不同測試類互相干擾
        if _is_ci_environment():
            session_id = _ci_deterministic_uuid(f"class:{test_class_name}")
            logger.info(
                f"CI 環境檢測到，使用確定性 Session ID: {session_id} (class: {test_class_name})"
            )
            return session_id

        return f"test_{test_class_name}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def generate_test_method_session_id(test_class_name: str, test_method_name: str) -> str:
        """
        為測試方法生成 session_id

        Args:
            test_class_name: 測試類名稱
            test_method_name: 測試方法名稱

        Returns:
            str: 唯一的 session_id
        """
        # 在 CI 環境中使用基於類名+方法名的確定性 session ID
        if _is_ci_environment():
            session_id = _ci_deterministic_uuid(f"method:{test_class_name}:{test_method_name}")
            logger.info(
                f"CI 環境檢測到，使用確定性 Session ID: {session_id} "
                f"(class: {test_class_name}, method: {test_method_name})"
            )
            return session_id

        return f"test_{test_class_name}_{test_method_name}_{uuid.uuid4().hex[:8]}"

    def register_session(
        self,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        註冊 session

        Args:
            session_id: session ID
            metadata: session 後設資料
        """
        self._session_registry[session_id] = {
            "created_at": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        logger.info(f"註冊 session: {session_id}")

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        獲取 session 資訊

        Args:
            session_id: session ID

        Returns:
            Optional[Dict[str, Any]]: session 信息
        """
        return self._session_registry.get(session_id)

    def cleanup_session(self, session_id: str) -> None:
        """
        清理 session

        Args:
            session_id: session ID
        """
        if session_id in self._session_registry:
            del self._session_registry[session_id]
            logger.info(f"清理 session: {session_id}")

    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        獲取所有 session

        Returns:
            Dict[str, Dict[str, Any]]: 所有 session
        """
        return self._session_registry.copy()


class SmartWaiter:
    """
    智能等待策略
    支援輪詢檢查、超時控制、指數退避
    """

    def __init__(
        self,
        default_timeout: float = 60.0,
        default_poll_interval: float = 1.0,
        max_poll_interval: float = 10.0,
        exponential_backoff: bool = True,
        backoff_factor: float = 2.0,
    ):
        """
        初始化智能等待器

        Args:
            default_timeout: 預設超時時間（秒）
            default_poll_interval: 預設輪詢間隔（秒）
            max_poll_interval: 最大輪詢間隔（秒）
            exponential_backoff: 是否使用指數退避
            backoff_factor: 退避因子
        """
        self.default_timeout = default_timeout
        self.default_poll_interval = default_poll_interval
        self.max_poll_interval = max_poll_interval
        self.exponential_backoff = exponential_backoff
        self.backoff_factor = backoff_factor

    def wait_for_condition(
        self,
        condition: Callable[[], bool],
        timeout: Optional[float] = None,
        poll_interval: Optional[float] = None,
        message: str = "等待條件滿足",
    ) -> bool:
        """
        等待條件滿足

        Args:
            condition: 條件函式，返回 True 表示條件滿足
            timeout: 超時時間（秒）
            poll_interval: 輪詢間隔（秒）
            message: 等待消息

        Returns:
            bool: 條件是否在超時前滿足
        """
        timeout = timeout or self.default_timeout
        poll_interval = poll_interval or self.default_poll_interval

        start_time = time.time()
        current_interval = poll_interval
        attempt = 0

        logger.info(f"開始等待: {message} (超時: {timeout}秒)")

        while time.time() - start_time < timeout:
            attempt += 1

            try:
                if condition():
                    elapsed = time.time() - start_time
                    logger.info(
                        f"✅ 條件滿足: {message} (耗時: {elapsed:.2f}秒, 嘗試次數: {attempt})"
                    )
                    return True
            except Exception as e:
                logger.warning(f"條件檢查異常 (嘗試 {attempt}): {e}")

            if self.exponential_backoff:
                current_interval = min(
                    current_interval * self.backoff_factor,
                    self.max_poll_interval,
                )

            time.sleep(current_interval)

        elapsed = time.time() - start_time
        logger.warning(f"❌ 等待超時: {message} (耗時: {elapsed:.2f}秒, 嘗試次數: {attempt})")
        return False

    def wait_for_response_keywords(
        self,
        get_response: Callable[[], Dict[str, Any]],
        keywords: List[str],
        timeout: Optional[float] = None,
        poll_interval: Optional[float] = None,
        require_all: bool = True,
        case_sensitive: bool = False,
    ) -> bool:
        """
        等待響應中包含指定關鍵詞

        Args:
            get_response: 獲取響應的函式
            keywords: 關鍵詞列表
            timeout: 超時時間（秒）
            poll_interval: 輪詢間隔（秒）
            require_all: 是否要求所有關鍵詞都出現
            case_sensitive: 是否區分大小寫

        Returns:
            bool: 是否在超時前找到關鍵詞
        """
        from utils.assertions import AssertionHelper

        def check_keywords() -> bool:
            response = get_response()
            return AssertionHelper.assert_keywords_in_response(
                response, keywords, require_all, case_sensitive
            )

        return self.wait_for_condition(
            check_keywords,
            timeout=timeout,
            poll_interval=poll_interval,
            message=f"等待響應包含關鍵詞: {keywords}",
        )

    def smart_wait(
        self,
        base_wait: float = 5.0,
        max_wait: float = 30.0,
        adaptive: bool = True,
    ) -> float:
        """
        智慧等待，根據歷史響應時間調整等待時間

        Args:
            base_wait: 基礎等待時間（秒）
            max_wait: 最大等待時間（秒）
            adaptive: 是否自適應調整

        Returns:
            float: 實際等待時間
        """
        wait_time = base_wait

        if adaptive:
            wait_time = min(wait_time * 1.2, max_wait)

        logger.info(f"智能等待 {wait_time:.1f} 秒...")
        time.sleep(wait_time)
        return wait_time


class RetryManager:
    """
    重試機制
    支援自定義重試條件、指數退避、最大重試次數
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_backoff: bool = True,
        backoff_factor: float = 2.0,
    ):
        """
        初始化重試管理器

        Args:
            max_retries: 最大重試次數
            base_delay: 基礎延遲（秒）
            max_delay: 最大延遲（秒）
            exponential_backoff: 是否使用指數退避
            backoff_factor: 退避因子
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_backoff = exponential_backoff
        self.backoff_factor = backoff_factor

    def retry_on_exception(
        self,
        exceptions: Union[type, tuple] = Exception,
        on_retry: Optional[Callable[[int, Exception], None]] = None,
    ) -> Callable:
        """
        裝飾器：在指定異常時重試

        Args:
            exceptions: 要捕獲的異常型別
            on_retry: 重試時的回呼函式

        Returns:
            Callable: 裝飾器函式
        """

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> T:
                last_exception = None
                delay = self.base_delay

                for attempt in range(self.max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e

                        if attempt < self.max_retries:
                            if on_retry:
                                on_retry(attempt + 1, e)

                            logger.warning(
                                f"重試 {attempt + 1}/{self.max_retries}: {func.__name__} - {e}"
                            )
                            time.sleep(delay)

                            if self.exponential_backoff:
                                delay = min(delay * self.backoff_factor, self.max_delay)
                        else:
                            logger.error(f"重試次數耗盡: {func.__name__} - {e}")
                            raise

                raise last_exception

            return wrapper

        return decorator

    def retry_on_result(
        self,
        condition: Callable[[Any], bool],
        max_retries: Optional[int] = None,
    ) -> Callable:
        """
        裝飾器：在結果滿足條件時重試

        Args:
            condition: 條件函式，返回 True 表示需要重試
            max_retries: 最大重試次數（覆蓋預設值）

        Returns:
            Callable: 裝飾器函式
        """
        retries = max_retries or self.max_retries

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> T:
                delay = self.base_delay
                last_result = None

                for attempt in range(retries + 1):
                    result = func(*args, **kwargs)
                    last_result = result

                    if not condition(result):
                        return result

                    if attempt < retries:
                        logger.warning(
                            f"結果不滿足條件，重試 {attempt + 1}/{retries}: {func.__name__}"
                        )
                        time.sleep(delay)

                        if self.exponential_backoff:
                            delay = min(delay * self.backoff_factor, self.max_delay)
                    else:
                        logger.warning(f"重試次數耗盡，返回最後結果: {func.__name__}")

                return last_result

            return wrapper

        return decorator

    def execute_with_retry(
        self,
        func: Callable[..., T],
        *args,
        exceptions: Union[type, tuple] = Exception,
        **kwargs,
    ) -> T:
        """
        執行函式並在異常時重試

        Args:
            func: 要執行的函式
            *args: 函式引數
            exceptions: 要捕獲的異常型別
            **kwargs: 函式關鍵字引數

        Returns:
            T: 函式返回值
        """

        @self.retry_on_exception(exceptions)
        def wrapped():
            return func(*args, **kwargs)

        return wrapped()


@dataclass
class TestData:
    """
    測試資料類
    用於管理測試資料
    """

    name: str
    description: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    expected_keywords: List[List[str]] = field(default_factory=list)
    expected_similarity: Optional[str] = None
    min_similarity: float = 0.6
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TestDataManager:
    """
    測試資料管理器
    支援從配置檔案載入、資料驗證、資料驅動測試
    """

    def __init__(self):
        self._data_registry: Dict[str, TestData] = {}

    def register_data(self, data: TestData) -> None:
        """
        註冊測試資料

        Args:
            data: 測試資料
        """
        self._data_registry[data.name] = data
        logger.info(f"註冊測試資料: {data.name}")

    def get_data(self, name: str) -> Optional[TestData]:
        """
        獲取測試資料

        Args:
            name: 資料名稱

        Returns:
            Optional[TestData]: 測試資料
        """
        return self._data_registry.get(name)

    def get_all_data(self) -> Dict[str, TestData]:
        """
        獲取所有測試資料

        Returns:
            Dict[str, TestData]: 所有測試資料
        """
        return self._data_registry.copy()

    def get_data_by_tag(self, tag: str) -> List[TestData]:
        """
        根據標籤獲取測試資料

        Args:
            tag: 標籤

        Returns:
            List[TestData]: 匹配的測試資料列表
        """
        return [data for data in self._data_registry.values() if tag in data.tags]

    def validate_data(self, data: TestData) -> bool:
        """
        驗證測試資料

        Args:
            data: 測試資料

        Returns:
            bool: 是否有效
        """
        if not data.name:
            logger.error("測試資料名稱不能為空")
            return False

        if not data.input_data:
            logger.warning(f"測試資料 {data.name} 沒有輸入資料")

        return True


DEFAULT_TEST_DATA = {
    "user_xiaoming": TestData(
        name="user_xiaoming",
        description="測試使用者小明",
        input_data={
            "message": "我叫小明，今年30歲，住在華東區，職業是測試開發",
        },
        expected_keywords=[
            ["小明", "測試開發", "30歲", "華東"],
        ],
        tags=["user", "basic"],
    ),
    "user_xiaohong": TestData(
        name="user_xiaohong",
        description="測試使用者小紅",
        input_data={
            "message": (
                "我叫小紅，今年25歲，住在華北區北京市朝陽區，職業是產品經理，"
                "喜歡美食和旅遊，不喜歡加班，我的生日是1999年8月15日"
            ),
        },
        expected_keywords=[
            ["產品經理"],
            ["1999", "8月", "8/15"],
            ["美食", "旅遊"],
        ],
        tags=["user", "rich"],
    ),
    "fruit_cherry": TestData(
        name="fruit_cherry",
        description="水果偏好 - 櫻桃",
        input_data={
            "message": "我喜歡吃櫻桃，日常喜歡喝美式咖啡",
        },
        expected_keywords=[
            ["櫻桃"],
            ["美式", "咖啡"],
        ],
        tags=["fruit", "drink"],
    ),
    "fruit_mango": TestData(
        name="fruit_mango",
        description="水果偏好 - 芒果",
        input_data={
            "message": "我喜歡吃芒果，日常喜歡喝拿鐵咖啡",
        },
        expected_keywords=[
            ["芒果"],
            ["拿鐵", "咖啡"],
        ],
        tags=["fruit", "drink"],
    ),
    "fruit_strawberry": TestData(
        name="fruit_strawberry",
        description="水果偏好 - 草莓",
        input_data={
            "message": "我喜歡吃草莓，日常喜歡喝抹茶拿鐵",
        },
        expected_keywords=[
            ["草莓"],
            ["抹茶", "拿鐵"],
        ],
        tags=["fruit", "drink"],
    ),
}


def get_default_data_manager() -> TestDataManager:
    """
    獲取預設的測試資料管理器

    Returns:
        TestDataManager: 測試資料管理器
    """
    manager = TestDataManager()
    for data in DEFAULT_TEST_DATA.values():
        manager.register_data(data)
    return manager
