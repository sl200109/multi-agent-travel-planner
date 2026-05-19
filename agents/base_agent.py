"""
所有规划 Agent 共用的基类。

这个文件的目标很简单：
把“统一入口”和“统一事件上报”这两件事集中处理，
这样每个具体 Agent 只需要关心自己的业务逻辑。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from models.schemas import PlanningEventType, TravelPlanState
from services.runtime import PlannerRuntime


class BaseAgent(ABC):
    """所有 Agent 的基础行为都定义在这里。"""

    # 每个子类都会覆盖自己的名字，方便日志和事件流识别来源。
    name: str = "BaseAgent"

    async def run(self, state: TravelPlanState, runtime: PlannerRuntime) -> TravelPlanState:
        """统一执行入口。

        对小白来说，可以把它理解成一个固定模板：
        1. 先发出“我开始工作了”的事件
        2. 再调用子类真正的业务逻辑
        3. 最后发出“我做完了”的事件

        这样做的好处是：
        - API 流式输出能看到每个 Agent 的开始和结束
        - UI 也能实时展示当前运行到哪一步
        - 各个 Agent 的写法会更统一
        """

        await runtime.emitter.emit(
            PlanningEventType.AGENT_STARTED,
            agent=self.name,
            message=f"{self.name} started",
        )

        # 这里会真正进入子类实现的 execute()。
        state = await self.execute(state, runtime)

        await runtime.emitter.emit(
            PlanningEventType.AGENT_COMPLETED,
            agent=self.name,
            message=f"{self.name} completed",
        )
        return state

    @abstractmethod
    async def execute(self, state: TravelPlanState, runtime: PlannerRuntime) -> TravelPlanState:
        """子类必须实现这个方法。

        run() 是统一模板，
        execute() 才是每个 Agent 自己真正干活的地方。
        """

    @staticmethod
    def format_sources(state_label: str, max_items: int = 5) -> str:
        """保留的简单辅助方法。

        目前这个方法没有承担很复杂的职责，
        只是保留一个统一入口，方便后面继续扩展来源格式化逻辑。
        """

        return state_label[: max_items * 200]
